#ifndef HELXAIRO_HID_CONTROLLER_HPP
#define HELXAIRO_HID_CONTROLLER_HPP

#include <Windows.h>
#include <string>
#include <vector>

namespace helxairo {

class HIDController {
public:
  HIDController();
  ~HIDController();

  bool connect();
  void disconnect();
  bool isConnected() const;

  // Connection info
  int getConnectionType(); // 0: None, 1: Wired, 2: Wireless

  // Hardware settings
  bool setButtonMapping(int index, int actionCode);
  int getBatteryLevel();
  int getActiveDpiStage();

  // DPI Settings
  bool setDpiStageValue(int index, int dpi);
  bool setCurrentDpiStage(int index);
  bool setDpiStagesCount(int count);
  bool setPollingRate(int rateHz);

  // Sensor Settings
  bool setLod(int lodValue);
  bool setRipple(bool enabled);
  bool setAngleSnapping(bool enabled);
  bool setMotionSync(bool enabled);
  bool setDebounceTime(int ms);
  bool setSensorMode(int mode);
  bool setHighestPerformance(bool enabled);
  bool setPerformanceTime(int val);

  // Lighting Settings
  bool setDpiColor(int stageIndex, int r, int g, int b);
  bool setDpiEffectMode(int mode);
  bool setDpiEffectBrightness(int level);
  bool setDpiEffectSpeed(int speed);

private:
  HANDLE m_handle = INVALID_HANDLE_VALUE;
  unsigned short m_vendorId = 0x3554;
  unsigned short m_productId = 0xF5D5;      // Wireless PID
  unsigned short m_productIdWired = 0xF511; // Wired PID
  unsigned short m_lastConnectedProductId = 0;

  static const unsigned char REPORT_ID = 0x08;
  static const size_t PAYLOAD_SIZE = 16;

  bool sendPacket(const std::vector<unsigned char> &packet);
  unsigned char calculateChecksum(const std::vector<unsigned char> &data);
  bool _sendHandshake();
  bool _sendPCDriverStatus(bool active);
  std::vector<unsigned char>
  _buildPacket(unsigned char command, unsigned short address,
               unsigned char length, const std::vector<unsigned char> &payload);

  bool _writeWithTimeout(const std::vector<unsigned char> &data,
                         DWORD timeoutMs);
  bool _readWithTimeout(std::vector<unsigned char> &buffer, DWORD timeoutMs);
};

} // namespace helxairo

#endif // HELXAIRO_HID_CONTROLLER_HPP
