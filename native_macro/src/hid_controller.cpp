#include "hid_controller.hpp"
#include <algorithm>
#include <iostream>
#include <random>
#include <setupapi.h>
#include <vector>

extern "C" {
#include <hidsdi.h>
}

namespace helxairo {

// Protocol Constants (Verified via controlhub.top)
enum HIDCommand : unsigned char {
  HANDSHAKE = 0x01,
  PC_DRIVER_STATUS = 0x02,
  DEVICE_ONLINE = 0x03,
  BATTERY = 0x04,
  WRITE_FLASH = 0x07,
  READ_FLASH = 0x08
};

// Memory Addresses (Verified via controlhub.top)
const unsigned short ADDR_DPI_STAGES_COUNT = 2;
const unsigned short ADDR_DPI_CURRENT_STAGE = 4;
const unsigned short ADDR_DPI_VALUES_BASE = 12;
const unsigned short ADDR_DPI_COLORS_BASE = 44;
const unsigned short ADDR_DPI_EFFECT_MODE = 76;
const unsigned short ADDR_DPI_EFFECT_BRIGHTNESS = 78;
const unsigned short ADDR_DPI_EFFECT_SPEED = 80;
const unsigned short ADDR_BUTTONS_BASE = 96;
const unsigned short ADDR_LOD = 10;
const unsigned short ADDR_POLLING_RATE = 0;

HIDController::HIDController() {
  m_handle = INVALID_HANDLE_VALUE;
  m_vendorId = 0x3554;
  m_productId = 0xF5D5;      // Wireless
  m_productIdWired = 0xF511; // Wired
}

HIDController::~HIDController() { disconnect(); }

bool HIDController::isConnected() const {
  return m_handle != INVALID_HANDLE_VALUE;
}

bool HIDController::connect() {
  if (isConnected())
    return true;

  GUID hidGuid;
  HidD_GetHidGuid(&hidGuid);

  HDEVINFO deviceInfoSet = SetupDiGetClassDevs(
      &hidGuid, NULL, NULL, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
  if (deviceInfoSet == INVALID_HANDLE_VALUE)
    return false;

  SP_DEVICE_INTERFACE_DATA interfaceData;
  interfaceData.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA);

  for (DWORD i = 0; SetupDiEnumDeviceInterfaces(deviceInfoSet, NULL, &hidGuid,
                                                i, &interfaceData);
       ++i) {
    DWORD detailSize = 0;
    SetupDiGetDeviceInterfaceDetail(deviceInfoSet, &interfaceData, NULL, 0,
                                    &detailSize, NULL);

    if (detailSize == 0)
      continue;

    std::vector<char> detailBuffer(detailSize);
    PSP_DEVICE_INTERFACE_DETAIL_DATA detailData =
        reinterpret_cast<PSP_DEVICE_INTERFACE_DETAIL_DATA>(detailBuffer.data());
    detailData->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA);

    if (SetupDiGetDeviceInterfaceDetail(deviceInfoSet, &interfaceData,
                                        detailData, detailSize, NULL, NULL)) {
      HANDLE tempHandle =
          CreateFile(detailData->DevicePath, GENERIC_READ | GENERIC_WRITE,
                     FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING,
                     FILE_FLAG_OVERLAPPED, NULL);

      if (tempHandle != INVALID_HANDLE_VALUE) {
        HIDD_ATTRIBUTES attr;
        attr.Size = sizeof(HIDD_ATTRIBUTES);
        if (HidD_GetAttributes(tempHandle, &attr)) {
          if (attr.VendorID == m_vendorId &&
              (attr.ProductID == m_productId ||
               attr.ProductID == m_productIdWired)) {

            // Check Usage Page (Fast fail)
            PHIDP_PREPARSED_DATA preparsedData;
            if (HidD_GetPreparsedData(tempHandle, &preparsedData)) {
              HIDP_CAPS caps;
              if (HidP_GetCaps(preparsedData, &caps) == HIDP_STATUS_SUCCESS) {
                if (caps.UsagePage == 0xFF02 || caps.UsagePage == 65282) {
                  m_handle = tempHandle; // Keep handle open
                  m_lastConnectedProductId = attr.ProductID;
                  /*
                  std::cout << "[HID] Connected to Furycube 0x" << std::hex
                            << attr.ProductID << std::dec << std::endl;
                  */

                  // Protocol Wake-up Sequence (with timeouts)
                  bool hs = _sendHandshake();
                  bool ds = _sendPCDriverStatus(true);
                  /*
                  std::cout << "[HID] Handshake: " << (hs ? "OK" : "FAIL")
                            << ", DriverStatus: " << (ds ? "OK" : "FAIL")
                            << std::endl;
                  */

                  HidD_FreePreparsedData(preparsedData);
                  SetupDiDestroyDeviceInfoList(deviceInfoSet);

                  // Set timeouts to prevent blocking
                  // We can't use SetCommTimeouts for HID, so we rely on
                  // Overlapped I/O

                  return true;
                }
              }
              HidD_FreePreparsedData(preparsedData);
            }
          }
        }
        CloseHandle(tempHandle);
      }
    }
  }

  SetupDiDestroyDeviceInfoList(deviceInfoSet);
  return false;
}

void HIDController::disconnect() {
  if (m_handle != INVALID_HANDLE_VALUE) {
    _sendPCDriverStatus(false);
    CloseHandle(m_handle);
    m_handle = INVALID_HANDLE_VALUE;
  }
}

int HIDController::getConnectionType() {
  // Return 0 immediately if not connected.
  // NEVER call connect() from here -- that causes recursive enumeration
  // when called from HardwareManager._check_connection().
  if (!isConnected())
    return 0;
  return (m_lastConnectedProductId == m_productIdWired) ? 1 : 2;
}

// Internal I/O Helpers
bool HIDController::_writeWithTimeout(const std::vector<unsigned char> &data,
                                      DWORD timeoutMs) {
  if (m_handle == INVALID_HANDLE_VALUE)
    return false;

  OVERLAPPED ol = {0};
  ol.hEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
  if (!ol.hEvent)
    return false;

  DWORD bytesWritten = 0;
  BOOL writeResult =
      WriteFile(m_handle, data.data(), (DWORD)data.size(), &bytesWritten, &ol);

  bool result = false;
  if (!writeResult && GetLastError() == ERROR_IO_PENDING) {
    if (WaitForSingleObject(ol.hEvent, timeoutMs) == WAIT_OBJECT_0) {
      GetOverlappedResult(m_handle, &ol, &bytesWritten, FALSE);
      result = (bytesWritten == data.size());
    } else {
      CancelIo(m_handle); // Timeout
    }
  } else {
    result = writeResult && (bytesWritten == data.size());
  }

  CloseHandle(ol.hEvent);
  return result;
}

bool HIDController::_readWithTimeout(std::vector<unsigned char> &buffer,
                                     DWORD timeoutMs) {
  if (m_handle == INVALID_HANDLE_VALUE)
    return false;

  OVERLAPPED ol = {0};
  ol.hEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
  if (!ol.hEvent)
    return false;

  DWORD bytesRead = 0;
  BOOL readResult =
      ReadFile(m_handle, buffer.data(), (DWORD)buffer.size(), &bytesRead, &ol);

  bool result = false;
  if (!readResult && GetLastError() == ERROR_IO_PENDING) {
    if (WaitForSingleObject(ol.hEvent, timeoutMs) == WAIT_OBJECT_0) {
      GetOverlappedResult(m_handle, &ol, &bytesRead, FALSE);
      result = (bytesRead > 0);
      // Note: We might read less than buffer.size(), that's fine for HID if we
      // verify content later
    } else {
      CancelIo(m_handle); // Timeout
    }
  } else {
    result = readResult && (bytesRead > 0);
  }

  CloseHandle(ol.hEvent);
  return result;
}

// Internal Protocol Helpers
std::vector<unsigned char>
HIDController::_buildPacket(unsigned char command, unsigned short address,
                            unsigned char length,
                            const std::vector<unsigned char> &payload) {
  std::vector<unsigned char> packet(PAYLOAD_SIZE, 0x00);
  packet[0] = command;
  packet[1] = 0x00;
  packet[2] = static_cast<unsigned char>((address >> 8) & 0xFF);
  packet[3] = static_cast<unsigned char>(address & 0xFF);
  packet[4] = length;

  for (size_t i = 0; i < payload.size() && i < 10; ++i) {
    packet[5 + i] = payload[i];
  }

  packet[15] = calculateChecksum(packet);
  return packet;
}

unsigned char
HIDController::calculateChecksum(const std::vector<unsigned char> &data) {
  unsigned int sum = 0;
  for (size_t i = 0; i < 15; ++i) {
    sum += data[i];
  }
  return static_cast<unsigned char>((85 - (sum & 0xFF) - REPORT_ID) & 0xFF);
}

bool HIDController::sendPacket(const std::vector<unsigned char> &packet) {
  if (!isConnected())
    return false;

  // Windows WriteFile expects ReportID as the first byte
  std::vector<unsigned char> report;
  report.reserve(1 + PAYLOAD_SIZE);
  report.push_back(REPORT_ID);
  report.insert(report.end(), packet.begin(), packet.end());

  return _writeWithTimeout(report, 100); // 100ms timeout for writing
}

bool HIDController::_sendHandshake() {
  std::random_device rd;
  std::mt19937 gen(rd());
  std::uniform_int_distribution<> dis(0, 255);

  std::vector<unsigned char> randBytes;
  for (int i = 0; i < 4; ++i)
    randBytes.push_back(static_cast<unsigned char>(dis(gen)));
  for (int i = 0; i < 4; ++i)
    randBytes.push_back(0x00);

  auto packet = _buildPacket(HANDSHAKE, 0x0000, 8, randBytes);
  return sendPacket(packet);
}

bool HIDController::_sendPCDriverStatus(bool active) {
  std::vector<unsigned char> payload = {
      static_cast<unsigned char>(active ? 1 : 0)};
  auto packet = _buildPacket(PC_DRIVER_STATUS, 0x0000, 1, payload);
  return sendPacket(packet);
}

// Public API
bool HIDController::setButtonMapping(int index, int actionCode) {
  unsigned short address = ADDR_BUTTONS_BASE + (index * 4);
  unsigned char type = 1; // Standard MouseKey
  unsigned char pLow = static_cast<unsigned char>(actionCode & 0xFF);
  unsigned char pHigh = static_cast<unsigned char>((actionCode >> 8) & 0xFF);
  unsigned char innerChecksum =
      static_cast<unsigned char>((85 - type - pLow - pHigh) & 0xFF);

  std::vector<unsigned char> payload = {type, pLow, pHigh, innerChecksum};
  auto packet = _buildPacket(WRITE_FLASH, address, 4, payload);
  return sendPacket(packet);
}

int HIDController::getBatteryLevel() {
  auto packet = _buildPacket(BATTERY, 0, 0, {});
  if (sendPacket(packet)) {
    // Read response using Overlapped I/O with timeout.
    // CRITICAL: Previous code used synchronous ReadFile(NULL overlapped)
    // which blocked the thread indefinitely if the mouse didn't respond.
    std::vector<unsigned char> response(33, 0x00);
    if (_readWithTimeout(response, 200)) { // 200ms timeout, non-blocking
      // response[0] = ReportID, response[1] = Cmd, response[6] = Percentage
      // Based on Webhub: payload[6] is raw percentage, [8-9] is voltage
      if (response[1] == BATTERY) {
        return static_cast<int>(response[6]);
      }
    }
  }
  return -1;
}

int HIDController::getActiveDpiStage() {
  auto packet = _buildPacket(READ_FLASH, ADDR_DPI_CURRENT_STAGE, 2, {});
  if (sendPacket(packet)) {
    // Read 33 bytes (1 report ID + 32 payload safety msg)
    std::vector<unsigned char> response(33, 0x00);

    if (_readWithTimeout(response, 100)) { // 100ms timeout
      if (response[1] == READ_FLASH) {
        return static_cast<int>(response[5]);
      }
    }
  }
  return 0; // Default to 0 if failed
}

bool HIDController::setDpiStageValue(int index, int dpi) {
  int rawValue = dpi / 50;
  unsigned char lowByte = rawValue & 0xFF;
  unsigned char highBits = (rawValue >> 8) & 0x03;
  unsigned char packedHigh = ((highBits << 2) | (highBits << 6)) & 0xFF;
  unsigned char innerChecksum =
      static_cast<unsigned char>((85 - lowByte - lowByte - packedHigh) & 0xFF);

  unsigned short address = ADDR_DPI_VALUES_BASE + (index * 4);
  std::vector<unsigned char> payload = {lowByte, lowByte, packedHigh,
                                        innerChecksum};

  auto packet = _buildPacket(WRITE_FLASH, address, 4, payload);
  return sendPacket(packet);
}

bool HIDController::setCurrentDpiStage(int index) {
  unsigned char val = static_cast<unsigned char>(index & 0xFF);
  unsigned char invVal = (85 - val) & 0xFF;
  std::vector<unsigned char> payload = {val, invVal};
  auto packet = _buildPacket(WRITE_FLASH, ADDR_DPI_CURRENT_STAGE, 2, payload);
  return sendPacket(packet);
}

bool HIDController::setDpiStagesCount(int count) {
  unsigned char val = static_cast<unsigned char>(count & 0xFF);
  unsigned char invVal = (85 - val) & 0xFF;
  std::vector<unsigned char> payload = {val, invVal};
  auto packet = _buildPacket(WRITE_FLASH, ADDR_DPI_STAGES_COUNT, 2, payload);
  return sendPacket(packet);
}

bool HIDController::setPollingRate(int rateHz) {
  int val = 1; // Default 1000Hz
  if (rateHz == 125)
    val = 8;
  else if (rateHz == 250)
    val = 4;
  else if (rateHz == 500)
    val = 2;
  else if (rateHz == 1000)
    val = 1;
  else if (rateHz == 2000)
    val = 32;
  else if (rateHz == 4000)
    val = 64;
  else if (rateHz == 8000)
    val = 128;

  unsigned char invVal = (85 - val) & 0xFF;
  std::vector<unsigned char> payload = {static_cast<unsigned char>(val),
                                        invVal};
  auto packet = _buildPacket(WRITE_FLASH, ADDR_POLLING_RATE, 2, payload);
  return sendPacket(packet);
}

bool HIDController::setLod(int lodValue) {
  unsigned char val = static_cast<unsigned char>(lodValue);
  unsigned char invVal = (85 - val) & 0xFF;
  std::vector<unsigned char> payload = {val, invVal};
  auto packet = _buildPacket(WRITE_FLASH, ADDR_LOD, 2, payload);
  return sendPacket(packet);
}

bool HIDController::setRipple(bool enabled) {
  unsigned char val = enabled ? 1 : 0;
  unsigned char invVal = (85 - val) & 0xFF;
  auto packet = _buildPacket(WRITE_FLASH, 177, 2, {val, invVal});
  return sendPacket(packet);
}

bool HIDController::setAngleSnapping(bool enabled) {
  unsigned char val = enabled ? 1 : 0;
  unsigned char invVal = (85 - val) & 0xFF;
  auto packet = _buildPacket(WRITE_FLASH, 175, 2, {val, invVal});
  return sendPacket(packet);
}

bool HIDController::setMotionSync(bool enabled) {
  unsigned char val = enabled ? 1 : 0;
  unsigned char invVal = (85 - val) & 0xFF;
  auto packet = _buildPacket(WRITE_FLASH, 171, 2, {val, invVal});
  return sendPacket(packet);
}

bool HIDController::setDebounceTime(int ms) {
  unsigned char val = static_cast<unsigned char>(ms);
  unsigned char invVal = (85 - val) & 0xFF;
  auto packet = _buildPacket(WRITE_FLASH, 169, 2, {val, invVal});
  return sendPacket(packet);
}

bool HIDController::setSensorMode(int mode) {
  unsigned char val = static_cast<unsigned char>(mode);
  unsigned char invVal = (85 - val) & 0xFF;
  auto packet = _buildPacket(WRITE_FLASH, 185, 2, {val, invVal});
  return sendPacket(packet);
}

bool HIDController::setHighestPerformance(bool enabled) {
  unsigned char val = enabled ? 1 : 0;
  unsigned char invVal = (85 - val) & 0xFF;
  auto packet = _buildPacket(WRITE_FLASH, 181, 2, {val, invVal});
  return sendPacket(packet);
}

bool HIDController::setPerformanceTime(int val) {
  unsigned char bVal = static_cast<unsigned char>(val);
  unsigned char invVal = (85 - bVal) & 0xFF;
  auto packet = _buildPacket(WRITE_FLASH, 183, 2, {bVal, invVal});
  return sendPacket(packet);
}

bool HIDController::setDpiColor(int stageIndex, int r, int g, int b) {
  unsigned char innerChecksum = (85 - r - g - b) & 0xFF;
  unsigned short address = ADDR_DPI_COLORS_BASE + (stageIndex * 4);
  std::vector<unsigned char> payload = {(unsigned char)r, (unsigned char)g,
                                        (unsigned char)b, innerChecksum};
  auto packet = _buildPacket(WRITE_FLASH, address, 4, payload);
  return sendPacket(packet);
}

bool HIDController::setDpiEffectMode(int mode) {
  unsigned char val = static_cast<unsigned char>(mode);
  unsigned char invVal = (85 - val) & 0xFF;
  auto packet =
      _buildPacket(WRITE_FLASH, ADDR_DPI_EFFECT_MODE, 2, {val, invVal});
  return sendPacket(packet);
}

bool HIDController::setDpiEffectBrightness(int level) {
  int mapping[] = {0, 16, 30, 60, 90, 128, 150, 180, 210, 230, 255};
  int byteVal = mapping[level > 10 ? 10 : (level < 1 ? 1 : level)];
  unsigned char invVal = (85 - byteVal) & 0xFF;
  auto packet = _buildPacket(WRITE_FLASH, ADDR_DPI_EFFECT_BRIGHTNESS, 2,
                             {(unsigned char)byteVal, invVal});
  return sendPacket(packet);
}

bool HIDController::setDpiEffectSpeed(int speed) {
  unsigned char val = static_cast<unsigned char>(speed);
  unsigned char invVal = (85 - val) & 0xFF;
  auto packet =
      _buildPacket(WRITE_FLASH, ADDR_DPI_EFFECT_SPEED, 2, {val, invVal});
  return sendPacket(packet);
}

} // namespace helxairo
