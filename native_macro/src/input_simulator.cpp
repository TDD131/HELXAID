#include "input_simulator.hpp"
#include <algorithm>
#include <cctype>
#include <chrono>
#include <thread>

namespace helxairo {

// All Windows constants (INPUT_MOUSE, INPUT_KEYBOARD, MOUSEEVENTF_*, etc.)
// are already defined in Windows.h - no need to redefine them

InputSimulator::InputSimulator() {
  m_screenWidth = GetSystemMetrics(SM_CXSCREEN);
  m_screenHeight = GetSystemMetrics(SM_CYSCREEN);
  initKeyMap();
}

void InputSimulator::initKeyMap() {
  // Letters
  for (char c = 'a'; c <= 'z'; ++c) {
    m_keyMap[std::string(1, c)] = 'A' + (c - 'a');
  }

  // Numbers
  for (char c = '0'; c <= '9'; ++c) {
    m_keyMap[std::string(1, c)] = c;
  }

  // Function keys
  for (int i = 1; i <= 24; ++i) {
    m_keyMap["f" + std::to_string(i)] = VK_F1 + (i - 1);
  }

  // Modifiers
  m_keyMap["ctrl"] = VK_CONTROL;
  m_keyMap["control"] = VK_CONTROL;
  m_keyMap["lctrl"] = VK_LCONTROL;
  m_keyMap["rctrl"] = VK_RCONTROL;
  m_keyMap["shift"] = VK_SHIFT;
  m_keyMap["lshift"] = VK_LSHIFT;
  m_keyMap["rshift"] = VK_RSHIFT;
  m_keyMap["alt"] = VK_MENU;
  m_keyMap["lalt"] = VK_LMENU;
  m_keyMap["ralt"] = VK_RMENU;
  m_keyMap["win"] = VK_LWIN;
  m_keyMap["lwin"] = VK_LWIN;
  m_keyMap["rwin"] = VK_RWIN;

  // Special keys
  m_keyMap["space"] = VK_SPACE;
  m_keyMap["enter"] = VK_RETURN;
  m_keyMap["return"] = VK_RETURN;
  m_keyMap["tab"] = VK_TAB;
  m_keyMap["escape"] = VK_ESCAPE;
  m_keyMap["esc"] = VK_ESCAPE;
  m_keyMap["backspace"] = VK_BACK;
  m_keyMap["delete"] = VK_DELETE;
  m_keyMap["del"] = VK_DELETE;
  m_keyMap["insert"] = VK_INSERT;
  m_keyMap["ins"] = VK_INSERT;
  m_keyMap["home"] = VK_HOME;
  m_keyMap["end"] = VK_END;
  m_keyMap["pageup"] = VK_PRIOR;
  m_keyMap["pagedown"] = VK_NEXT;
  m_keyMap["pgup"] = VK_PRIOR;
  m_keyMap["pgdn"] = VK_NEXT;
  m_keyMap["capslock"] = VK_CAPITAL;
  m_keyMap["caps"] = VK_CAPITAL;
  m_keyMap["numlock"] = VK_NUMLOCK;
  m_keyMap["scrolllock"] = VK_SCROLL;
  m_keyMap["printscreen"] = VK_SNAPSHOT;
  m_keyMap["pause"] = VK_PAUSE;

  // Arrow keys
  m_keyMap["up"] = VK_UP;
  m_keyMap["down"] = VK_DOWN;
  m_keyMap["left"] = VK_LEFT;
  m_keyMap["right"] = VK_RIGHT;

  // Numpad
  for (int i = 0; i <= 9; ++i) {
    m_keyMap["num" + std::to_string(i)] = VK_NUMPAD0 + i;
    m_keyMap["numpad" + std::to_string(i)] = VK_NUMPAD0 + i;
  }
  m_keyMap["numplus"] = VK_ADD;
  m_keyMap["numminus"] = VK_SUBTRACT;
  m_keyMap["nummultiply"] = VK_MULTIPLY;
  m_keyMap["numdivide"] = VK_DIVIDE;
  m_keyMap["numdecimal"] = VK_DECIMAL;
  m_keyMap["numenter"] = VK_RETURN;

  // Punctuation
  m_keyMap[";"] = VK_OEM_1;
  m_keyMap["="] = VK_OEM_PLUS;
  m_keyMap[","] = VK_OEM_COMMA;
  m_keyMap["-"] = VK_OEM_MINUS;
  m_keyMap["."] = VK_OEM_PERIOD;
  m_keyMap["/"] = VK_OEM_2;
  m_keyMap["`"] = VK_OEM_3;
  m_keyMap["["] = VK_OEM_4;
  m_keyMap["\\"] = VK_OEM_5;
  m_keyMap["]"] = VK_OEM_6;
  m_keyMap["'"] = VK_OEM_7;
}

void InputSimulator::sendInputs(INPUT *inputs, size_t count) {
  SendInput(static_cast<UINT>(count), inputs, sizeof(INPUT));
}

void InputSimulator::mouseMove(int x, int y, bool absolute) {
  INPUT input = {0};
  input.type = INPUT_MOUSE;

  if (absolute) {
    // Convert to normalized coordinates (0-65535)
    input.mi.dx = static_cast<LONG>((x * 65535) / m_screenWidth);
    input.mi.dy = static_cast<LONG>((y * 65535) / m_screenHeight);
    input.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE;
  } else {
    input.mi.dx = x;
    input.mi.dy = y;
    input.mi.dwFlags = MOUSEEVENTF_MOVE;
  }

  sendInputs(&input, 1);
}

void InputSimulator::mouseMoveRelative(int dx, int dy) {
  INPUT input = {0};
  input.type = INPUT_MOUSE;
  input.mi.dx = dx;
  input.mi.dy = dy;
  input.mi.dwFlags = MOUSEEVENTF_MOVE;

  sendInputs(&input, 1);
}

std::pair<DWORD, DWORD> InputSimulator::getMouseFlags(const std::string &button,
                                                      bool down) const {
  std::string btn = button;
  std::transform(btn.begin(), btn.end(), btn.begin(), ::tolower);

  DWORD flags = 0;
  DWORD data = 0;

  if (btn == "left") {
    flags = down ? MOUSEEVENTF_LEFTDOWN : MOUSEEVENTF_LEFTUP;
  } else if (btn == "right") {
    flags = down ? MOUSEEVENTF_RIGHTDOWN : MOUSEEVENTF_RIGHTUP;
  } else if (btn == "middle") {
    flags = down ? MOUSEEVENTF_MIDDLEDOWN : MOUSEEVENTF_MIDDLEUP;
  } else if (btn == "x1") {
    flags = down ? MOUSEEVENTF_XDOWN : MOUSEEVENTF_XUP;
    data = XBUTTON1;
  } else if (btn == "x2") {
    flags = down ? MOUSEEVENTF_XDOWN : MOUSEEVENTF_XUP;
    data = XBUTTON2;
  }

  return {flags, data};
}

void InputSimulator::mouseDown(const std::string &button) {
  auto [flags, data] = getMouseFlags(button, true);

  INPUT input = {0};
  input.type = INPUT_MOUSE;
  input.mi.dwFlags = flags;
  input.mi.mouseData = data;

  sendInputs(&input, 1);
}

void InputSimulator::mouseUp(const std::string &button) {
  auto [flags, data] = getMouseFlags(button, false);

  INPUT input = {0};
  input.type = INPUT_MOUSE;
  input.mi.dwFlags = flags;
  input.mi.mouseData = data;

  sendInputs(&input, 1);
}

void InputSimulator::mouseClick(const std::string &button, int count) {
  for (int i = 0; i < count; ++i) {
    mouseDown(button);
    mouseUp(button);
  }
}

void InputSimulator::mouseScroll(int delta, bool horizontal) {
  INPUT input = {0};
  input.type = INPUT_MOUSE;
  input.mi.dwFlags = horizontal ? MOUSEEVENTF_HWHEEL : MOUSEEVENTF_WHEEL;
  input.mi.mouseData = static_cast<DWORD>(delta);

  sendInputs(&input, 1);
}

uint16_t InputSimulator::getVkCode(const std::string &key) const {
  std::string lowerKey = key;
  std::transform(lowerKey.begin(), lowerKey.end(), lowerKey.begin(), ::tolower);

  auto it = m_keyMap.find(lowerKey);
  if (it != m_keyMap.end()) {
    return it->second;
  }

  // Try single character
  if (lowerKey.length() == 1) {
    char c = std::toupper(lowerKey[0]);
    return static_cast<uint16_t>(c);
  }

  return 0;
}

void InputSimulator::keyDown(const std::string &key) {
  uint16_t vk = getVkCode(key);
  if (vk == 0)
    return;

  INPUT input = {0};
  input.type = INPUT_KEYBOARD;
  input.ki.wVk = vk;
  input.ki.wScan = static_cast<WORD>(MapVirtualKey(vk, MAPVK_VK_TO_VSC));

  // Extended key flag for certain keys
  if (vk >= VK_PRIOR && vk <= VK_DELETE) {
    input.ki.dwFlags = KEYEVENTF_EXTENDEDKEY;
  }

  sendInputs(&input, 1);
}

void InputSimulator::keyUp(const std::string &key) {
  uint16_t vk = getVkCode(key);
  if (vk == 0)
    return;

  INPUT input = {0};
  input.type = INPUT_KEYBOARD;
  input.ki.wVk = vk;
  input.ki.wScan = static_cast<WORD>(MapVirtualKey(vk, MAPVK_VK_TO_VSC));
  input.ki.dwFlags = KEYEVENTF_KEYUP;

  if (vk >= VK_PRIOR && vk <= VK_DELETE) {
    input.ki.dwFlags |= KEYEVENTF_EXTENDEDKEY;
  }

  sendInputs(&input, 1);
}

void InputSimulator::keyTap(const std::string &key, int holdMs) {
  keyDown(key);
  if (holdMs > 0) {
    std::this_thread::sleep_for(std::chrono::milliseconds(holdMs));
  }
  keyUp(key);
}

void InputSimulator::keyCombo(const std::vector<std::string> &keys,
                              int holdMs) {
  // Press all keys
  for (const auto &key : keys) {
    keyDown(key);
  }

  if (holdMs > 0) {
    std::this_thread::sleep_for(std::chrono::milliseconds(holdMs));
  }

  // Release in reverse order
  for (auto it = keys.rbegin(); it != keys.rend(); ++it) {
    keyUp(*it);
  }
}

void InputSimulator::typeText(const std::string &text, int intervalMs) {
  for (size_t i = 0; i < text.length(); ++i) {
    wchar_t ch = static_cast<wchar_t>(text[i]);

    INPUT inputs[2] = {0};

    // Key down
    inputs[0].type = INPUT_KEYBOARD;
    inputs[0].ki.wScan = ch;
    inputs[0].ki.dwFlags = KEYEVENTF_UNICODE;

    // Key up
    inputs[1].type = INPUT_KEYBOARD;
    inputs[1].ki.wScan = ch;
    inputs[1].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;

    sendInputs(inputs, 2);

    if (intervalMs > 0 && i < text.length() - 1) {
      std::this_thread::sleep_for(std::chrono::milliseconds(intervalMs));
    }
  }
}

std::pair<int, int> InputSimulator::getCursorPosition() const {
  POINT pt;
  GetCursorPos(&pt);
  return {pt.x, pt.y};
}

bool InputSimulator::isKeyPressed(const std::string &key) const {
  uint16_t vk = getVkCode(key);
  if (vk == 0)
    return false;
  return (GetAsyncKeyState(vk) & 0x8000) != 0;
}

bool InputSimulator::isMouseButtonPressed(const std::string &button) const {
  std::string btn = button;
  std::transform(btn.begin(), btn.end(), btn.begin(), ::tolower);

  int vk = 0;
  if (btn == "left")
    vk = VK_LBUTTON;
  else if (btn == "right")
    vk = VK_RBUTTON;
  else if (btn == "middle")
    vk = VK_MBUTTON;
  else if (btn == "x1")
    vk = VK_XBUTTON1;
  else if (btn == "x2")
    vk = VK_XBUTTON2;

  if (vk == 0)
    return false;
  return (GetAsyncKeyState(vk) & 0x8000) != 0;
}

} // namespace helxairo
