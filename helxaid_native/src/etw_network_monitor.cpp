#include "etw_network_monitor.h"

// NOMINMAX prevents min/max macros from Windows.h
#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <Windows.h>
#include <evntrace.h>
#include <tdh.h>

#include <chrono>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <unordered_map>

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "tdh.lib")

namespace helxaid {

namespace {

static uint64_t now_millis() {
  using namespace std::chrono;
  return duration_cast<milliseconds>(steady_clock::now().time_since_epoch())
      .count();
}

static std::wstring widen(const std::string &s) {
  if (s.empty())
    return std::wstring();
  int len = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0);
  if (len <= 0)
    return std::wstring();
  std::wstring out;
  out.resize(static_cast<size_t>(len - 1));
  MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, out.data(), len);
  return out;
}

static std::string narrow(const std::wstring &w) {
  if (w.empty())
    return std::string();
  int len = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, nullptr, 0, nullptr,
                                nullptr);
  if (len <= 0)
    return std::string();
  std::string out;
  out.resize(static_cast<size_t>(len - 1));
  WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, out.data(), len, nullptr,
                      nullptr);
  return out;
}

static bool extract_uint32_property(PEVENT_RECORD event,
                                   const wchar_t *property_name,
                                   uint32_t &out) {
  if (!event || !property_name)
    return false;

  DWORD bufferSize = 0;
  auto status = TdhGetEventInformation(
      event, 0, nullptr,
      reinterpret_cast<PTRACE_EVENT_INFO>(nullptr), &bufferSize);
  if (status != ERROR_INSUFFICIENT_BUFFER || bufferSize == 0)
    return false;

  std::vector<uint8_t> infoBuf;
  infoBuf.resize(bufferSize);
  auto *info = reinterpret_cast<PTRACE_EVENT_INFO>(infoBuf.data());
  status = TdhGetEventInformation(event, 0, nullptr, info, &bufferSize);
  if (status != ERROR_SUCCESS)
    return false;

  for (ULONG i = 0; i < info->TopLevelPropertyCount; ++i) {
    auto &prop = info->EventPropertyInfoArray[i];
    if (prop.NameOffset == 0)
      continue;

    const wchar_t *name = reinterpret_cast<const wchar_t *>(
        reinterpret_cast<const uint8_t *>(info) + prop.NameOffset);
    if (!name)
      continue;

    if (_wcsicmp(name, property_name) != 0)
      continue;

    PROPERTY_DATA_DESCRIPTOR desc;
    desc.PropertyName = reinterpret_cast<ULONGLONG>(name);
    desc.ArrayIndex = ULONG_MAX;

    ULONG valueSize = 0;
    status = TdhGetPropertySize(event, 0, nullptr, 1, &desc, &valueSize);
    if (status != ERROR_SUCCESS || valueSize == 0)
      return false;

    std::vector<uint8_t> valueBuf;
    valueBuf.resize(valueSize);
    status = TdhGetProperty(event, 0, nullptr, 1, &desc, valueSize,
                            valueBuf.data());
    if (status != ERROR_SUCCESS)
      return false;

    if (valueSize >= sizeof(uint32_t)) {
      out = *reinterpret_cast<uint32_t *>(valueBuf.data());
      return true;
    }
    return false;
  }

  return false;
}

static std::string win_error_message(ULONG code) {
  LPWSTR buf = nullptr;
  DWORD flags = FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
                FORMAT_MESSAGE_IGNORE_INSERTS;
  DWORD len = FormatMessageW(flags, nullptr, code,
                             MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
                             reinterpret_cast<LPWSTR>(&buf), 0, nullptr);
  if (len == 0 || !buf)
    return std::string();
  std::wstring wmsg(buf, buf + len);
  LocalFree(buf);
  // Trim trailing newlines.
  while (!wmsg.empty() && (wmsg.back() == L'\r' || wmsg.back() == L'\n')) {
    wmsg.pop_back();
  }
  return narrow(wmsg);
}

} // namespace

class ETWNetworkMonitor::Impl {
public:
  std::atomic<bool> running{false};
  std::thread worker;

  std::wstring sessionName;
  TRACEHANDLE sessionHandle = 0;
  TRACEHANDLE traceHandle = 0;

  mutable std::shared_mutex statsMutex;
  std::unordered_map<uint32_t, ProcessNetworkStats> pidStats;

  std::function<std::string(uint32_t)> processNameResolver;
  std::function<std::string(uint32_t)> processPathResolver;

  mutable std::mutex errorMutex;
  std::string lastError;

  static void WINAPI eventRecordCallback(PEVENT_RECORD event);
  void onEvent(const EVENT_RECORD *event);

  bool startSession(const ETWConfig &config);
  void stopSession();
  void traceLoop();

  void setError(const std::string &msg) {
    std::lock_guard<std::mutex> lk(errorMutex);
    lastError = msg;
  }

  std::string getError() const {
    std::lock_guard<std::mutex> lk(errorMutex);
    return lastError;
  }
};

void WINAPI ETWNetworkMonitor::Impl::eventRecordCallback(PEVENT_RECORD event) {
  if (!event || !event->UserContext)
    return;
  auto *impl = reinterpret_cast<ETWNetworkMonitor::Impl *>(event->UserContext);
  impl->onEvent(event);
}

void ETWNetworkMonitor::Impl::onEvent(const EVENT_RECORD *event) {
  if (!event)
    return;

  // The classic TCPIP kernel events use opcodes:
  // TCP Send: 10 (IPv4), 12 (IPv6)
  // TCP Recv: 11 (IPv4), 13 (IPv6)
  // UDP Send: 26
  // UDP Recv: 27
  const uint16_t eventId = event->EventHeader.EventDescriptor.Id;

  bool isSend = false;
  bool isRecv = false;

  switch (eventId) {
  case 10:
  case 12:
  case 26:
    isSend = true;
    break;
  case 11:
  case 13:
  case 27:
    isRecv = true;
    break;
  default:
    return;
  }

  const uint32_t pid = event->EventHeader.ProcessId;
  if (pid == 0)
    return;

  uint32_t size = 0;

  // Prefer TDH property lookup for robustness.
  // Common property name for these events is "size".
  if (!extract_uint32_property(const_cast<EVENT_RECORD *>(event), L"size", size)) {
    // Fallback: some classic events store the first 4 bytes as the length.
    if (event->UserData && event->UserDataLength >= sizeof(uint32_t)) {
      size = *reinterpret_cast<const uint32_t *>(event->UserData);
    } else {
      return;
    }
  }

  std::string name;
  std::string path;
  if (processNameResolver) {
    try {
      name = processNameResolver(pid);
    } catch (...) {
    }
  }
  if (processPathResolver) {
    try {
      path = processPathResolver(pid);
    } catch (...) {
    }
  }

  {
    std::unique_lock<std::shared_mutex> lk(statsMutex);
    auto &s = pidStats[pid];
    s.pid = pid;
    if (!name.empty())
      s.process_name = name;
    if (!path.empty())
      s.exe_path = path;
    s.last_update = now_millis();
    if (isSend)
      s.bytes_sent += size;
    if (isRecv)
      s.bytes_recv += size;
  }
}

bool ETWNetworkMonitor::Impl::startSession(const ETWConfig &config) {
  // Kernel TCP/IP events are part of the classic NT Kernel Logger provider.
  // For EnableFlags (EVENT_TRACE_FLAG_*) to take effect, the session must use
  // the SystemTraceControlGuid.
  const GUID SystemTraceControlGuid = {0x9e814aad,
                                       0x3204,
                                       0x11d2,
                                       {0x9a, 0x82, 0x00, 0x60, 0x08, 0xa8,
                                        0x69, 0x39}};

  // Use the standard kernel logger name to maximize compatibility.
  sessionName = L"NT Kernel Logger";

  // Allocate EVENT_TRACE_PROPERTIES with room for the session name.
  const ULONG loggerNameBytes =
      static_cast<ULONG>((sessionName.size() + 1) * sizeof(wchar_t));
  const ULONG logFileNameBytes = static_cast<ULONG>(sizeof(wchar_t));
  const ULONG propsSize =
      sizeof(EVENT_TRACE_PROPERTIES) + loggerNameBytes + logFileNameBytes;

  std::vector<uint8_t> propsBuf;
  propsBuf.resize(propsSize);
  auto *props = reinterpret_cast<EVENT_TRACE_PROPERTIES *>(propsBuf.data());
  ZeroMemory(props, propsSize);

  props->Wnode.BufferSize = propsSize;
  props->Wnode.Flags = WNODE_FLAG_TRACED_GUID;
  props->Wnode.Guid = SystemTraceControlGuid;
  props->Wnode.ClientContext = 1; // QPC clock resolution

  props->LogFileMode = EVENT_TRACE_REAL_TIME_MODE;
  props->LoggerNameOffset = sizeof(EVENT_TRACE_PROPERTIES);
  props->LogFileNameOffset = sizeof(EVENT_TRACE_PROPERTIES) + loggerNameBytes;

  props->BufferSize = config.buffer_size_kb;
  props->MinimumBuffers = config.buffer_count;
  props->MaximumBuffers = config.buffer_count;
  props->FlushTimer = config.flush_interval_ms;
  props->EnableFlags = EVENT_TRACE_FLAG_NETWORK_TCPIP;

  auto *loggerName = reinterpret_cast<wchar_t *>(propsBuf.data() +
                                                 props->LoggerNameOffset);
  wcsncpy_s(loggerName, sessionName.size() + 1, sessionName.c_str(),
            sessionName.size());

  auto *logFileName = reinterpret_cast<wchar_t *>(propsBuf.data() +
                                                  props->LogFileNameOffset);
  logFileName[0] = L'\0';

  ULONG status = StartTraceW(&sessionHandle, sessionName.c_str(), props);
  if (status == ERROR_ALREADY_EXISTS) {
    // Attempt to stop stale session from previous crash and retry.
    ControlTraceW(0, sessionName.c_str(), props, EVENT_TRACE_CONTROL_STOP);
    status = StartTraceW(&sessionHandle, sessionName.c_str(), props);
  }

  if (status != ERROR_SUCCESS) {
    std::string msg = win_error_message(status);
    if (status == ERROR_ACCESS_DENIED) {
      if (!msg.empty())
        msg += " ";
      msg += "(Run as Administrator to enable ETW kernel network tracing)";
    }
    if (msg.empty()) {
      setError("StartTraceW failed: " + std::to_string(status));
    } else {
      setError("StartTraceW failed: " + std::to_string(status) + " (" + msg + ")");
    }
    sessionHandle = 0;
    return false;
  }

  return true;
}

void ETWNetworkMonitor::Impl::stopSession() {
  if (sessionHandle) {
    EVENT_TRACE_PROPERTIES props;
    ZeroMemory(&props, sizeof(props));
    props.Wnode.BufferSize = sizeof(props);
    ControlTraceW(sessionHandle, sessionName.c_str(), &props,
                  EVENT_TRACE_CONTROL_STOP);
    sessionHandle = 0;
  }
}

void ETWNetworkMonitor::Impl::traceLoop() {
  EVENT_TRACE_LOGFILEW log;
  ZeroMemory(&log, sizeof(log));

  log.LoggerName = const_cast<LPWSTR>(sessionName.c_str());
  log.ProcessTraceMode = PROCESS_TRACE_MODE_REAL_TIME | PROCESS_TRACE_MODE_EVENT_RECORD;
  log.EventRecordCallback = &ETWNetworkMonitor::Impl::eventRecordCallback;
  log.Context = this;

  traceHandle = OpenTraceW(&log);
  if (traceHandle == INVALID_PROCESSTRACE_HANDLE) {
    setError("OpenTraceW failed");
    return;
  }

  // ProcessTrace blocks until the session is stopped.
  ULONG status = ProcessTrace(&traceHandle, 1, nullptr, nullptr);
  (void)status;

  CloseTrace(traceHandle);
  traceHandle = 0;
}

ETWNetworkMonitor::ETWNetworkMonitor() : m_impl(std::make_unique<Impl>()) {}

ETWNetworkMonitor::~ETWNetworkMonitor() { stop(); }

bool ETWNetworkMonitor::start(const ETWConfig &config) {
  if (!m_impl)
    return false;
  if (m_impl->running)
    return true;

  m_impl->setError(std::string());

  if (!m_impl->startSession(config)) {
    return false;
  }

  m_impl->running = true;
  m_impl->worker = std::thread([this]() { m_impl->traceLoop(); });
  return true;
}

void ETWNetworkMonitor::stop() {
  if (!m_impl)
    return;

  if (!m_impl->running)
    return;

  m_impl->running = false;
  m_impl->stopSession();

  if (m_impl->worker.joinable())
    m_impl->worker.join();
}

bool ETWNetworkMonitor::isRunning() const {
  return m_impl && m_impl->running;
}

std::vector<ProcessNetworkStats> ETWNetworkMonitor::getProcessStats() const {
  std::vector<ProcessNetworkStats> out;
  if (!m_impl)
    return out;

  std::shared_lock<std::shared_mutex> lk(m_impl->statsMutex);
  out.reserve(m_impl->pidStats.size());
  for (auto &kv : m_impl->pidStats) {
    out.push_back(kv.second);
  }
  return out;
}

void ETWNetworkMonitor::reset() {
  if (!m_impl)
    return;
  std::unique_lock<std::shared_mutex> lk(m_impl->statsMutex);
  m_impl->pidStats.clear();
}

void ETWNetworkMonitor::setProcessNameResolver(
    std::function<std::string(uint32_t)> resolver) {
  if (!m_impl)
    return;
  m_impl->processNameResolver = std::move(resolver);
}

void ETWNetworkMonitor::setProcessPathResolver(
    std::function<std::string(uint32_t)> resolver) {
  if (!m_impl)
    return;
  m_impl->processPathResolver = std::move(resolver);
}

std::string ETWNetworkMonitor::getLastError() const {
  if (!m_impl)
    return std::string();
  return m_impl->getError();
}

} // namespace helxaid
