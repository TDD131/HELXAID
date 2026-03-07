/**
 * HID Controller Header
 *
 * Native HID communication for Furycube mouse.
 */

#pragma once

#include <atomic>
#include <mutex>
#include <string>
#include <vector>
#include <windows.h>


namespace helxaid {

class HIDController {
public:
  HIDController();
  ~HIDController();

  bool connect();
  void disconnect();
  bool isConnected() const { return m_connected; }

  std::string getConnectionType() const { return m_connectionType; }

  // Hardware commands
  bool setButtonMapping(int buttonIndex, int actionCode);
  bool setDpiStageValue(int stageIndex, int dpi);
  bool setPollingRate(int rateHz);
  bool setDpiColor(int stageIndex, int r, int g, int b);

  // State polling
  int getBatteryLevel();
  int getActiveDpiStage();

private:
  bool sendPacket(BYTE cmd, WORD address, BYTE length, const BYTE *payload,
                  int payloadLen);
  BYTE calculateChecksum(const BYTE *data);

  HANDLE m_device{INVALID_HANDLE_VALUE};
  std::atomic<bool> m_connected{false};
  std::string m_connectionType{"unknown"};
  std::mutex m_mutex;

  const USHORT VID = 0x3554;
  const USHORT PID_WIRELESS = 0xF5D5;
  const USHORT PID_WIRED = 0xF5D6; // Example, check actual wired PID
};

} // namespace helxaid
