#pragma once
#include <Windows.h>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>


namespace helxairo {

/**
 * InputSimulator - High-performance input injection.
 *
 * Uses Windows SendInput API for reliable, low-latency simulation.
 * Supports mouse movement, clicks, scrolling, and keyboard input.
 *
 * Performance: <0.5ms per operation with batch support.
 */
class InputSimulator {
public:
  InputSimulator();

  // ==================== MOUSE ====================

  /**
   * Move mouse to absolute screen position.
   * @param x X coordinate (0 = left edge)
   * @param y Y coordinate (0 = top edge)
   * @param absolute If true, coordinates are absolute screen position
   */
  void mouseMove(int x, int y, bool absolute = true);

  /**
   * Move mouse by relative offset from current position.
   * @param dx Horizontal offset (positive = right)
   * @param dy Vertical offset (positive = down)
   */
  void mouseMoveRelative(int dx, int dy);

  /**
   * Press mouse button down.
   * @param button Button name: "left", "right", "middle", "x1", "x2"
   */
  void mouseDown(const std::string &button = "left");

  /**
   * Release mouse button.
   * @param button Button name: "left", "right", "middle", "x1", "x2"
   */
  void mouseUp(const std::string &button = "left");

  /**
   * Click mouse button (press + release).
   * @param button Button name
   * @param count Number of clicks
   */
  void mouseClick(const std::string &button = "left", int count = 1);

  /**
   * Scroll mouse wheel.
   * @param delta Scroll amount (positive = up/right, negative = down/left)
   * @param horizontal If true, scroll horizontally
   */
  void mouseScroll(int delta, bool horizontal = false);

  // ==================== KEYBOARD ====================

  /**
   * Press key down.
   * @param key Key name (e.g., "a", "space", "ctrl", "f1")
   */
  void keyDown(const std::string &key);

  /**
   * Release key.
   * @param key Key name
   */
  void keyUp(const std::string &key);

  /**
   * Press and release a key.
   * @param key Key name
   * @param holdMs Milliseconds to hold before releasing
   */
  void keyTap(const std::string &key, int holdMs = 0);

  /**
   * Press a key combination (e.g., Ctrl+Shift+A).
   * Keys are pressed in order and released in reverse order.
   * @param keys Vector of key names
   * @param holdMs Milliseconds to hold after all keys pressed
   */
  void keyCombo(const std::vector<std::string> &keys, int holdMs = 0);

  /**
   * Type a string of text using Unicode input.
   * @param text Text to type
   * @param intervalMs Delay between characters
   */
  void typeText(const std::string &text, int intervalMs = 0);

  // ==================== STATE QUERIES ====================

  /**
   * Get current cursor position.
   * @return Pair of (x, y) screen coordinates
   */
  std::pair<int, int> getCursorPosition() const;

  /**
   * Check if a key is currently pressed.
   * @param key Key name
   * @return True if key is down
   */
  bool isKeyPressed(const std::string &key) const;

  /**
   * Check if a mouse button is currently pressed.
   * @param button Button name
   * @return True if button is down
   */
  bool isMouseButtonPressed(const std::string &button) const;

private:
  // Send array of INPUT structs to Windows
  void sendInputs(INPUT *inputs, size_t count);

  // Convert key name to virtual key code
  uint16_t getVkCode(const std::string &key) const;

  // Get mouse event flags for button
  std::pair<DWORD, DWORD> getMouseFlags(const std::string &button,
                                        bool down) const;

  // Initialize key name to VK code mapping
  void initKeyMap();

  int m_screenWidth;
  int m_screenHeight;
  std::unordered_map<std::string, uint16_t> m_keyMap;
};

} // namespace helxairo
