#include "input_hook.hpp"
#include <iostream>

namespace helxairo {

// Static members
InputHook *InputHook::s_instance = nullptr;
LARGE_INTEGER InputHook::s_frequency = {0};
bool InputHook::s_frequencyInitialized = false;

// Use Windows API constants directly - they're in Windows.h
// WM_LBUTTONDOWN, WM_LBUTTONUP, etc. are already defined
// VK_LCONTROL, VK_RCONTROL, etc. are already defined

// Modifier mask bits (our own constants, not Windows)
constexpr uint32_t HELX_MOD_CTRL = 0x01;
constexpr uint32_t HELX_MOD_SHIFT = 0x02;
constexpr uint32_t HELX_MOD_ALT = 0x04;
constexpr uint32_t HELX_MOD_WIN = 0x08;

// Hook flags (our own prefixed names to avoid conflicts)

InputHook::InputHook() {
  // Initialize performance counter frequency
  if (!s_frequencyInitialized) {
    QueryPerformanceFrequency(&s_frequency);
    s_frequencyInitialized = true;
  }
}

InputHook::~InputHook() { stop(); }

void InputHook::start() {
  if (m_running.load())
    return;

  s_instance = this;
  m_running.store(true);

  m_thread = std::thread(&InputHook::hookThread, this);
}

void InputHook::stop() {
  if (!m_running.load())
    return;

  m_running.store(false);

  // Post quit message to hook thread
  if (m_threadId != 0) {
    PostThreadMessage(m_threadId, WM_QUIT, 0, 0);
  }

  if (m_thread.joinable()) {
    m_thread.join();
  }

  s_instance = nullptr;
}

void InputHook::setMouseCallback(MouseCallback cb) {
  std::lock_guard<std::mutex> lock(m_mutex);
  m_mouseCallback = std::move(cb);
}

void InputHook::setKeyboardCallback(KeyboardCallback cb) {
  std::lock_guard<std::mutex> lock(m_mutex);
  m_keyboardCallback = std::move(cb);
}

void InputHook::suppressButton(MouseButton button, bool suppress) {
  std::lock_guard<std::mutex> lock(m_mutex);
  if (suppress) {
    m_suppressedButtons.insert(static_cast<int>(button));
  } else {
    m_suppressedButtons.erase(static_cast<int>(button));
  }
}

void InputHook::suppressKey(uint32_t vkCode, bool suppress) {
  std::lock_guard<std::mutex> lock(m_mutex);
  if (suppress) {
    m_suppressedKeys.insert(vkCode);
  } else {
    m_suppressedKeys.erase(vkCode);
  }
}

void InputHook::clearSuppressions() {
  std::lock_guard<std::mutex> lock(m_mutex);
  m_suppressedButtons.clear();
  m_suppressedKeys.clear();
}

bool InputHook::isModifierHeld(uint32_t vkCode) const {
  uint32_t mask = m_modifierMask.load();

  switch (vkCode) {
  case VK_CONTROL:
  case VK_LCONTROL:
  case VK_RCONTROL:
    return (mask & HELX_MOD_CTRL) != 0;
  case VK_SHIFT:
  case VK_LSHIFT:
  case VK_RSHIFT:
    return (mask & HELX_MOD_SHIFT) != 0;
  case VK_MENU:
  case VK_LMENU:
  case VK_RMENU:
    return (mask & HELX_MOD_ALT) != 0;
  case VK_LWIN:
  case VK_RWIN:
    return (mask & HELX_MOD_WIN) != 0;
  default:
    return false;
  }
}

uint32_t InputHook::getModifierMask() const { return m_modifierMask.load(); }

uint64_t InputHook::getTimestamp() {
  LARGE_INTEGER now;
  QueryPerformanceCounter(&now);
  return static_cast<uint64_t>(now.QuadPart * 1000000 / s_frequency.QuadPart);
}

void InputHook::hookThread() {
  m_threadId = GetCurrentThreadId();

  // Install hooks
  m_mouseHook = SetWindowsHookExW(WH_MOUSE_LL, mouseProc, nullptr, 0);

  m_keyboardHook = SetWindowsHookExW(WH_KEYBOARD_LL, keyboardProc, nullptr, 0);

  if (m_mouseHook && m_keyboardHook) {
    std::cout << "[InputHook] Hooks installed successfully" << std::endl;
  } else {
    std::cerr << "[InputHook] Failed to install hooks" << std::endl;
    m_running.store(false);
    return;
  }

  // Message loop
  MSG msg;
  while (m_running.load() && GetMessage(&msg, nullptr, 0, 0)) {
    TranslateMessage(&msg);
    DispatchMessage(&msg);
  }

  // Unhook
  if (m_mouseHook) {
    UnhookWindowsHookEx(m_mouseHook);
    m_mouseHook = nullptr;
  }
  if (m_keyboardHook) {
    UnhookWindowsHookEx(m_keyboardHook);
    m_keyboardHook = nullptr;
  }

  std::cout << "[InputHook] Hooks removed" << std::endl;
}

LRESULT CALLBACK InputHook::mouseProc(int nCode, WPARAM wParam, LPARAM lParam) {
  if (nCode >= 0 && s_instance) {
    auto *data = reinterpret_cast<MSLLHOOKSTRUCT_STRUCT *>(lParam);
    if (s_instance->processMouseEvent(wParam, data)) {
      return 1; // Suppress
    }
  }
  return CallNextHookEx(nullptr, nCode, wParam, lParam);
}

LRESULT CALLBACK InputHook::keyboardProc(int nCode, WPARAM wParam,
                                         LPARAM lParam) {
  if (nCode >= 0 && s_instance) {
    auto *data = reinterpret_cast<KBDLLHOOKSTRUCT_STRUCT *>(lParam);
    if (s_instance->processKeyboardEvent(wParam, data)) {
      return 1; // Suppress
    }
  }
  return CallNextHookEx(nullptr, nCode, wParam, lParam);
}

bool InputHook::processMouseEvent(WPARAM wParam, MSLLHOOKSTRUCT_STRUCT *data) {
  MouseEvent event;
  event.x = data->pt.x;
  event.y = data->pt.y;
  event.delta = 0;
  event.timestamp = getTimestamp();
  event.injected = (data->flags & LLMHF_INJECTED) != 0;

  // Determine event type and button
  switch (wParam) {
  case WM_LBUTTONDOWN:
    event.type = EventType::MouseDown;
    event.button = MouseButton::Left;
    break;
  case WM_LBUTTONUP:
    event.type = EventType::MouseUp;
    event.button = MouseButton::Left;
    break;
  case WM_RBUTTONDOWN:
    event.type = EventType::MouseDown;
    event.button = MouseButton::Right;
    break;
  case WM_RBUTTONUP:
    event.type = EventType::MouseUp;
    event.button = MouseButton::Right;
    break;
  case WM_MBUTTONDOWN:
    event.type = EventType::MouseDown;
    event.button = MouseButton::Middle;
    break;
  case WM_MBUTTONUP:
    event.type = EventType::MouseUp;
    event.button = MouseButton::Middle;
    break;
  case WM_XBUTTONDOWN:
    event.type = EventType::MouseDown;
    event.button = (HIWORD(data->mouseData) == XBUTTON1) ? MouseButton::X1
                                                         : MouseButton::X2;
    break;
  case WM_XBUTTONUP:
    event.type = EventType::MouseUp;
    event.button = (HIWORD(data->mouseData) == XBUTTON1) ? MouseButton::X1
                                                         : MouseButton::X2;
    break;
  case WM_MOUSEWHEEL:
    event.type = EventType::MouseScroll;
    event.delta = static_cast<int16_t>(HIWORD(data->mouseData));
    event.button = MouseButton::Middle;
    break;
  case WM_MOUSEMOVE:
    if (!s_instance->m_listenToMove.load())
      return false;
    event.type = EventType::MouseMove;
    break;
  default:
    return false;
  }

  // Check suppression list
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_suppressedButtons.count(static_cast<int>(event.button))) {
      return true;
    }
  }

  // Call callback
  bool suppress = false;
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_mouseCallback) {
      suppress = m_mouseCallback(event);
    }
  }

  return suppress;
}

bool InputHook::processKeyboardEvent(WPARAM wParam,
                                     KBDLLHOOKSTRUCT_STRUCT *data) {
  KeyboardEvent event;
  event.vkCode = data->vkCode;
  event.scanCode = data->scanCode;
  event.timestamp = getTimestamp();
  event.injected = (data->flags & LLKHF_INJECTED) != 0;

  // Determine event type
  if (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN) {
    event.type = EventType::KeyDown;
  } else if (wParam == WM_KEYUP || wParam == WM_SYSKEYUP) {
    event.type = EventType::KeyUp;
  } else {
    return false;
  }

  // Update modifier state
  uint32_t mask = m_modifierMask.load();
  bool isDown = (event.type == EventType::KeyDown);

  switch (data->vkCode) {
  case VK_LCONTROL:
  case VK_RCONTROL:
  case VK_CONTROL:
    if (isDown)
      mask |= HELX_MOD_CTRL;
    else
      mask &= ~HELX_MOD_CTRL;
    break;
  case VK_LSHIFT:
  case VK_RSHIFT:
  case VK_SHIFT:
    if (isDown)
      mask |= HELX_MOD_SHIFT;
    else
      mask &= ~HELX_MOD_SHIFT;
    break;
  case VK_LMENU:
  case VK_RMENU:
  case VK_MENU:
    if (isDown)
      mask |= HELX_MOD_ALT;
    else
      mask &= ~HELX_MOD_ALT;
    break;
  case VK_LWIN:
  case VK_RWIN:
    if (isDown)
      mask |= HELX_MOD_WIN;
    else
      mask &= ~HELX_MOD_WIN;
    break;
  }
  m_modifierMask.store(mask);

  // Check suppression list
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_suppressedKeys.count(data->vkCode)) {
      return true;
    }
  }

  // Call callback
  bool suppress = false;
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_keyboardCallback) {
      suppress = m_keyboardCallback(event);
    }
  }

  return suppress;
}

} // namespace helxairo
