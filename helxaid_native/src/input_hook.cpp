/**
 * Input Hook Implementation
 *
 * Zero-latency C++ implementation of low-level Windows hooks.
 */

#include "input_hook.h"
#include <iostream>

namespace helxaid {

InputHook *InputHook::s_instance = nullptr;

InputHook::InputHook() {
  s_instance = this;
  for (int i = 0; i < 256; ++i)
    m_modifiers[i] = false;
}

InputHook::~InputHook() {
  stop();
  s_instance = nullptr;
}

bool InputHook::start() {
  if (m_running)
    return true;

  m_running = true;
  m_hookThread = std::thread(&InputHook::messageLoop, this);

  // Wait for thread to start and hooks to be set
  int retry = 0;
  while (m_threadId == 0 && retry++ < 100) {
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }

  return m_threadId != 0;
}

void InputHook::stop() {
  if (!m_running)
    return;

  m_running = false;
  if (m_threadId != 0) {
    PostThreadMessage(m_threadId, WM_QUIT, 0, 0);
  }

  if (m_hookThread.joinable()) {
    m_hookThread.join();
  }

  m_threadId = 0;
}

void InputHook::messageLoop() {
  m_threadId = GetCurrentThreadId();

  m_mouseHook =
      SetWindowsHookEx(WH_MOUSE_LL, MouseProc, GetModuleHandle(NULL), 0);
  m_keyboardHook =
      SetWindowsHookEx(WH_KEYBOARD_LL, KeyboardProc, GetModuleHandle(NULL), 0);

  if (!m_mouseHook || !m_keyboardHook) {
    m_running = false;
    return;
  }

  MSG msg;
  while (GetMessage(&msg, NULL, 0, 0)) {
    TranslateMessage(&msg);
    DispatchMessage(&msg);
  }

  UnhookWindowsHookEx(m_mouseHook);
  UnhookWindowsHookEx(m_keyboardHook);
  m_mouseHook = NULL;
  m_keyboardHook = NULL;
}

LRESULT CALLBACK InputHook::MouseProc(int nCode, WPARAM wParam, LPARAM lParam) {
  if (nCode == HC_ACTION && s_instance) {
    MSLLHOOKSTRUCT *pMouse = reinterpret_cast<MSLLHOOKSTRUCT *>(lParam);

    // Fast path for mouse move
    if (wParam == WM_MOUSEMOVE && !s_instance->m_listenToMove) {
      return CallNextHookEx(s_instance->m_mouseHook, nCode, wParam, lParam);
    }

    MouseEvent ev;
    ev.x = pMouse->pt.x;
    ev.y = pMouse->pt.y;
    ev.timestamp = pMouse->time;
    ev.isMove = (wParam == WM_MOUSEMOVE);
    ev.button = MouseButton::None;
    ev.isDown = false;

    switch (wParam) {
    case WM_LBUTTONDOWN:
      ev.button = MouseButton::Left;
      ev.isDown = true;
      break;
    case WM_LBUTTONUP:
      ev.button = MouseButton::Left;
      ev.isDown = false;
      break;
    case WM_RBUTTONDOWN:
      ev.button = MouseButton::Right;
      ev.isDown = true;
      break;
    case WM_RBUTTONUP:
      ev.button = MouseButton::Right;
      ev.isDown = false;
      break;
    case WM_MBUTTONDOWN:
      ev.button = MouseButton::Middle;
      ev.isDown = true;
      break;
    case WM_MBUTTONUP:
      ev.button = MouseButton::Middle;
      ev.isDown = false;
      break;
    case WM_XBUTTONDOWN:
      ev.button = (HIWORD(pMouse->mouseData) == XBUTTON1) ? MouseButton::X1
                                                          : MouseButton::X2;
      ev.isDown = true;
      break;
    case WM_XBUTTONUP:
      ev.button = (HIWORD(pMouse->mouseData) == XBUTTON1) ? MouseButton::X1
                                                          : MouseButton::X2;
      ev.isDown = false;
      break;
    }

    if (s_instance->m_mouseCallback) {
      if (s_instance->m_mouseCallback(ev))
        return 1; // Suppress
    }
  }
  return CallNextHookEx(s_instance->m_mouseHook, nCode, wParam, lParam);
}

LRESULT CALLBACK InputHook::KeyboardProc(int nCode, WPARAM wParam,
                                         LPARAM lParam) {
  if (nCode == HC_ACTION && s_instance) {
    KBDLLHOOKSTRUCT *pKey = reinterpret_cast<KBDLLHOOKSTRUCT *>(lParam);

    bool isDown = (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN);
    int vkCode = pKey->vkCode;

    // Update modifier cache instantly
    if (vkCode < 256) {
      s_instance->m_modifiers[vkCode] = isDown;
    }

    if (s_instance->m_keyboardCallback) {
      KeyboardEvent ev;
      ev.vkCode = vkCode;
      ev.isDown = isDown;
      ev.timestamp = pKey->time;

      if (s_instance->m_keyboardCallback(ev))
        return 1; // Suppress
    }
  }
  return CallNextHookEx(s_instance->m_keyboardHook, nCode, wParam, lParam);
}

bool InputHook::getModifierState(int vkCode) {
  if (vkCode >= 0 && vkCode < 256) {
    return m_modifiers[vkCode];
  }
  return false;
}

} // namespace helxaid
