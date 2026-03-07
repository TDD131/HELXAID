/*
 * FurycubeHID.cpp - Native Windows HID Communication for Furycube Mouse
 *
 * Fast C++ implementation for direct USB HID communication with Furycube mouse.
 * Called from Python via subprocess for low-latency hardware control.
 *
 * Protocol (reverse-engineered from controlhub.top/Furycube):
 * - Report ID: 8
 * - Packet Size: 16 bytes
 * - Checksum: (85 - Sum of Bytes 0-14) - 8
 *
 * Device IDs:
 * - VID: 0x3554 (13652)
 * - PID: 0xF5D5 (62933)
 *
 * Usage:
 *   FurycubeHID.exe list              - List connected devices
 *   FurycubeHID.exe connect           - Connect to device
 *   FurycubeHID.exe button <idx> <action>  - Set button mapping
 *   FurycubeHID.exe battery           - Read battery level
 *
 * Compile: cl /EHsc FurycubeHID.cpp /link setupapi.lib hid.lib
 */

#include <cstring>
#include <iostream>
#include <setupapi.h>
#include <string>
#include <vector>
#include <windows.h>


// Manual HID function declarations (to avoid hidsdi.h SDK issues)
extern "C" {
typedef struct _HIDD_ATTRIBUTES {
  ULONG Size;
  USHORT VendorID;
  USHORT ProductID;
  USHORT VersionNumber;
} HIDD_ATTRIBUTES, *PHIDD_ATTRIBUTES;

void __stdcall HidD_GetHidGuid(LPGUID HidGuid);
BOOLEAN __stdcall HidD_GetAttributes(HANDLE HidDeviceObject,
                                     PHIDD_ATTRIBUTES Attributes);
BOOLEAN __stdcall HidD_GetProductString(HANDLE HidDeviceObject, PVOID Buffer,
                                        ULONG BufferLength);
BOOLEAN __stdcall HidD_SetFeature(HANDLE HidDeviceObject, PVOID ReportBuffer,
                                  ULONG ReportBufferLength);
BOOLEAN __stdcall HidD_GetFeature(HANDLE HidDeviceObject, PVOID ReportBuffer,
                                  ULONG ReportBufferLength);
BOOLEAN __stdcall HidD_SetOutputReport(HANDLE HidDeviceObject,
                                       PVOID ReportBuffer,
                                       ULONG ReportBufferLength);
}

#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "hid.lib")

// Device identifiers
const USHORT FURYCUBE_VID = 0x3554;
const USHORT FURYCUBE_PID = 0xF5D5;

// HID Protocol constants
const BYTE REPORT_ID = 8;
const BYTE CMD_WRITE_FLASH = 0x07;
const BYTE CMD_READ_FLASH = 0x08;
const WORD BUTTON_CONFIG_BASE_ADDR = 96;
const BYTE BUTTON_CONFIG_SIZE = 4;

// Global device handle
HANDLE g_deviceHandle = INVALID_HANDLE_VALUE;

/**
 * Calculate the Furycube protocol checksum for a packet.
 * Formula: (85 - Sum of Bytes 0-14) - 8
 *
 * @param data Pointer to 15 bytes of packet data (excluding checksum)
 * @return Calculated checksum byte
 */
BYTE calculateChecksum(const BYTE *data) {
  int sum = 0;
  for (int i = 0; i < 15; i++) {
    sum += data[i];
  }
  return (BYTE)((85 - sum - 8) & 0xFF);
}

/**
 * Build a 16-byte HID packet for Furycube protocol.
 *
 * @param cmd Command byte (CMD_WRITE_FLASH or CMD_READ_FLASH)
 * @param address 16-bit memory address in flash
 * @param length Number of payload bytes
 * @param payload Pointer to payload data
 * @param payloadLen Length of payload array
 * @param packet Output buffer (must be 17 bytes: 1 report ID + 16 data)
 */
void buildPacket(BYTE cmd, WORD address, BYTE length, const BYTE *payload,
                 int payloadLen, BYTE *packet) {
  // First byte is report ID
  packet[0] = REPORT_ID;

  // Byte 1: Command
  packet[1] = cmd;

  // Byte 2: Reserved
  packet[2] = 0;

  // Bytes 3-4: Address (Big Endian)
  packet[3] = (address >> 8) & 0xFF;
  packet[4] = address & 0xFF;

  // Byte 5: Data length
  packet[5] = length;

  // Bytes 6-15: Payload (padded with zeros)
  memset(&packet[6], 0, 10);
  for (int i = 0; i < payloadLen && i < 10; i++) {
    packet[6 + i] = payload[i];
  }

  // Byte 16: Checksum (calculated on bytes 1-15)
  packet[16] = calculateChecksum(&packet[1]);
}

/**
 * Find and open the Furycube device by VID/PID.
 *
 * @return True if device found and opened, false otherwise
 */
bool openDevice() {
  GUID hidGuid;
  HidD_GetHidGuid(&hidGuid);

  HDEVINFO deviceInfoSet = SetupDiGetClassDevs(
      &hidGuid, NULL, NULL, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);

  if (deviceInfoSet == INVALID_HANDLE_VALUE) {
    std::cerr << "ERROR: Failed to get device info set" << std::endl;
    return false;
  }

  SP_DEVICE_INTERFACE_DATA deviceInterfaceData;
  deviceInterfaceData.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA);

  int deviceIndex = 0;
  bool found = false;

  while (SetupDiEnumDeviceInterfaces(deviceInfoSet, NULL, &hidGuid, deviceIndex,
                                     &deviceInterfaceData)) {

    // Get required buffer size
    DWORD requiredSize = 0;
    SetupDiGetDeviceInterfaceDetail(deviceInfoSet, &deviceInterfaceData, NULL,
                                    0, &requiredSize, NULL);

    // Allocate buffer
    PSP_DEVICE_INTERFACE_DETAIL_DATA detailData =
        (PSP_DEVICE_INTERFACE_DETAIL_DATA)malloc(requiredSize);
    detailData->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA);

    // Get device path
    if (SetupDiGetDeviceInterfaceDetail(deviceInfoSet, &deviceInterfaceData,
                                        detailData, requiredSize, NULL, NULL)) {

      // Try to open the device
      HANDLE testHandle = CreateFile(
          detailData->DevicePath, GENERIC_READ | GENERIC_WRITE,
          FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);

      if (testHandle != INVALID_HANDLE_VALUE) {
        // Check VID/PID
        HIDD_ATTRIBUTES attrs;
        attrs.Size = sizeof(HIDD_ATTRIBUTES);

        if (HidD_GetAttributes(testHandle, &attrs)) {
          if (attrs.VendorID == FURYCUBE_VID &&
              attrs.ProductID == FURYCUBE_PID) {
            g_deviceHandle = testHandle;
            found = true;

            // Get product name
            wchar_t productName[256] = {0};
            if (HidD_GetProductString(testHandle, productName,
                                      sizeof(productName))) {
              std::wcout << L"CONNECTED: " << productName << std::endl;
            } else {
              std::cout << "CONNECTED: Furycube Mouse" << std::endl;
            }

            free(detailData);
            SetupDiDestroyDeviceInfoList(deviceInfoSet);
            return true;
          }
        }
        CloseHandle(testHandle);
      }
    }

    free(detailData);
    deviceIndex++;
  }

  SetupDiDestroyDeviceInfoList(deviceInfoSet);

  if (!found) {
    std::cerr << "ERROR: Furycube device not found" << std::endl;
    std::cerr << "Make sure the 2.4G wireless receiver is plugged in."
              << std::endl;
  }

  return false;
}

/**
 * Close the device handle.
 */
void closeDevice() {
  if (g_deviceHandle != INVALID_HANDLE_VALUE) {
    CloseHandle(g_deviceHandle);
    g_deviceHandle = INVALID_HANDLE_VALUE;
    std::cout << "DISCONNECTED" << std::endl;
  }
}

/**
 * Send a HID Feature Report to the device.
 * Uses HidD_SetFeature which corresponds to WebHID's sendFeatureReport.
 *
 * @param packet 17-byte packet (report ID + 16 data bytes)
 * @return True if sent successfully
 */
bool sendReport(const BYTE *packet) {
  if (g_deviceHandle == INVALID_HANDLE_VALUE) {
    std::cerr << "ERROR: Device not connected" << std::endl;
    return false;
  }

  // Use SetFeature for feature reports (matches WebHID sendFeatureReport)
  BOOL result = HidD_SetFeature(g_deviceHandle, (PVOID)packet, 17);

  if (!result) {
    std::cerr << "ERROR: Failed to send feature report (code " << GetLastError()
              << ")" << std::endl;
    return false;
  }

  // Print packet for debugging
  std::cout << "SENT: ";
  for (int i = 0; i < 17; i++) {
    printf("%02X ", packet[i]);
  }
  std::cout << std::endl;

  return true;
}

/**
 * Read a HID report from the device.
 *
 * @param buffer Output buffer for received data
 * @param bufferSize Size of output buffer
 * @param timeout Timeout in milliseconds
 * @return Number of bytes read, or -1 on error
 */
int readReport(BYTE *buffer, int bufferSize, DWORD timeout = 500) {
  if (g_deviceHandle == INVALID_HANDLE_VALUE) {
    return -1;
  }

  DWORD bytesRead = 0;
  BOOL result = ReadFile(g_deviceHandle, buffer, bufferSize, &bytesRead, NULL);

  if (!result) {
    return -1;
  }

  return (int)bytesRead;
}

/**
 * Set button mapping on the mouse.
 *
 * @param buttonIndex Button index (0-4)
 * @param actionCode Action code to assign
 * @return True if successful
 */
bool setButtonMapping(int buttonIndex, int actionCode) {
  if (buttonIndex < 0 || buttonIndex > 4) {
    std::cerr << "ERROR: Invalid button index (0-4)" << std::endl;
    return false;
  }

  // Calculate address for this button
  WORD address = BUTTON_CONFIG_BASE_ADDR + (buttonIndex * BUTTON_CONFIG_SIZE);

  // Build payload: [type, param_high, param_low, sub_checksum]
  BYTE keyType = 1; // Mouse Key Function
  BYTE paramHigh = 0;
  BYTE paramLow = (BYTE)actionCode;
  BYTE subChecksum = (keyType + paramHigh + paramLow + 83) & 0xFF;

  BYTE payload[4] = {keyType, paramHigh, paramLow, subChecksum};

  // Build and send packet
  BYTE packet[17];
  buildPacket(CMD_WRITE_FLASH, address, 4, payload, 4, packet);

  if (sendReport(packet)) {
    std::cout << "OK: Button " << (buttonIndex + 1) << " mapped to action "
              << actionCode << std::endl;
    return true;
  }

  return false;
}

/**
 * List all connected Furycube devices.
 */
void listDevices() {
  GUID hidGuid;
  HidD_GetHidGuid(&hidGuid);

  HDEVINFO deviceInfoSet = SetupDiGetClassDevs(
      &hidGuid, NULL, NULL, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);

  if (deviceInfoSet == INVALID_HANDLE_VALUE) {
    std::cerr << "ERROR: Failed to enumerate devices" << std::endl;
    return;
  }

  SP_DEVICE_INTERFACE_DATA deviceInterfaceData;
  deviceInterfaceData.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA);

  int deviceIndex = 0;
  int furycubeCount = 0;

  std::cout << "Scanning for Furycube devices..." << std::endl;

  while (SetupDiEnumDeviceInterfaces(deviceInfoSet, NULL, &hidGuid, deviceIndex,
                                     &deviceInterfaceData)) {

    DWORD requiredSize = 0;
    SetupDiGetDeviceInterfaceDetail(deviceInfoSet, &deviceInterfaceData, NULL,
                                    0, &requiredSize, NULL);

    PSP_DEVICE_INTERFACE_DETAIL_DATA detailData =
        (PSP_DEVICE_INTERFACE_DETAIL_DATA)malloc(requiredSize);
    detailData->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA);

    if (SetupDiGetDeviceInterfaceDetail(deviceInfoSet, &deviceInterfaceData,
                                        detailData, requiredSize, NULL, NULL)) {

      HANDLE testHandle = CreateFile(
          detailData->DevicePath, GENERIC_READ | GENERIC_WRITE,
          FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);

      if (testHandle != INVALID_HANDLE_VALUE) {
        HIDD_ATTRIBUTES attrs;
        attrs.Size = sizeof(HIDD_ATTRIBUTES);

        if (HidD_GetAttributes(testHandle, &attrs)) {
          if (attrs.VendorID == FURYCUBE_VID &&
              attrs.ProductID == FURYCUBE_PID) {

            wchar_t productName[256] = {0};
            HidD_GetProductString(testHandle, productName, sizeof(productName));

            std::wcout << L"[" << furycubeCount << L"] " << productName
                       << L" (VID:" << std::hex << attrs.VendorID << L" PID:"
                       << attrs.ProductID << L")" << std::dec << std::endl;
            furycubeCount++;
          }
        }
        CloseHandle(testHandle);
      }
    }

    free(detailData);
    deviceIndex++;
  }

  SetupDiDestroyDeviceInfoList(deviceInfoSet);

  if (furycubeCount == 0) {
    std::cout << "No Furycube devices found." << std::endl;
  } else {
    std::cout << "Found " << furycubeCount << " Furycube device(s)."
              << std::endl;
  }
}

/**
 * Print usage information.
 */
void printUsage() {
  std::cout << "Furycube HID Controller - Native C++ USB Communication"
            << std::endl;
  std::cout << std::endl;
  std::cout << "Usage:" << std::endl;
  std::cout << "  FurycubeHID.exe list              - List connected devices"
            << std::endl;
  std::cout << "  FurycubeHID.exe button <idx> <action> - Set button mapping"
            << std::endl;
  std::cout << "                                      idx: 0-4 (button index)"
            << std::endl;
  std::cout << "                                      action: 1=Left, 2=Right, "
               "4=Middle,"
            << std::endl;
  std::cout
      << "                                              8=Forward, 16=Backward"
      << std::endl;
  std::cout << std::endl;
  std::cout << "Examples:" << std::endl;
  std::cout << "  FurycubeHID.exe list" << std::endl;
  std::cout << "  FurycubeHID.exe button 3 1    # Set button 4 (Forward) to "
               "Left Click"
            << std::endl;
}

/**
 * Main entry point.
 * Parses command line arguments and executes requested action.
 */
int main(int argc, char *argv[]) {
  if (argc < 2) {
    printUsage();
    return 1;
  }

  std::string command = argv[1];

  if (command == "list") {
    // List all Furycube devices
    listDevices();
    return 0;
  } else if (command == "button") {
    // Set button mapping: button <index> <action>
    if (argc < 4) {
      std::cerr << "ERROR: Missing arguments for button command" << std::endl;
      std::cerr << "Usage: FurycubeHID.exe button <index> <action>"
                << std::endl;
      return 1;
    }

    int buttonIndex = atoi(argv[2]);
    int actionCode = atoi(argv[3]);

    if (!openDevice()) {
      return 1;
    }

    bool success = setButtonMapping(buttonIndex, actionCode);
    closeDevice();

    return success ? 0 : 1;
  } else if (command == "help" || command == "-h" || command == "--help") {
    printUsage();
    return 0;
  } else {
    std::cerr << "ERROR: Unknown command '" << command << "'" << std::endl;
    printUsage();
    return 1;
  }

  return 0;
}
