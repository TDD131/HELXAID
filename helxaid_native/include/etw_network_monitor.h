#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace helxaid {

struct ProcessNetworkStats {
  uint32_t pid = 0;
  std::string process_name;
  std::string exe_path;
  uint64_t bytes_sent = 0;
  uint64_t bytes_recv = 0;
  uint64_t last_update = 0;
};

struct ETWConfig {
  uint32_t buffer_size_kb = 64;
  uint32_t buffer_count = 12;
  uint32_t flush_interval_ms = 1000;
};

class ETWNetworkMonitor {
public:
  ETWNetworkMonitor();
  ~ETWNetworkMonitor();

  bool start(const ETWConfig &config = ETWConfig());
  void stop();
  bool isRunning() const;

  std::vector<ProcessNetworkStats> getProcessStats() const;
  void reset();

  void setProcessNameResolver(std::function<std::string(uint32_t)> resolver);
  void setProcessPathResolver(std::function<std::string(uint32_t)> resolver);

  std::string getLastError() const;

private:
  class Impl;
  std::unique_ptr<Impl> m_impl;

  ETWNetworkMonitor(const ETWNetworkMonitor &) = delete;
  ETWNetworkMonitor &operator=(const ETWNetworkMonitor &) = delete;
};

} // namespace helxaid
