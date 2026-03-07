/**
 * Input Hook Header
 * 
 * High-performance low-level Windows hooks for mouse and keyboard.
 */

#pragma once

#include <windows.h>
#include <functional>
#include <mutex>
#include <thread>
#include <atomic>
#include <vector>

namespace helxaid {

enum class MouseButton {
    None = 0,
    Left = 1,
    Right = 2,
    Middle = 3,
    X1 = 4,
    X2 = 5
};

struct MouseEvent {
    int x;
    int y;
    MouseButton button;
    bool isDown;
    bool isMove;
    DWORD timestamp;
};

struct KeyboardEvent {
    int vkCode;
    bool isDown;
    DWORD timestamp;
};

class InputHook {
public:
    using MouseCallback = std::function<bool(const MouseEvent&)>;
    using KeyboardCallback = std::function<bool(const KeyboardEvent&)>;

    InputHook();
    ~InputHook();

    bool start();
    void stop();
    bool isRunning() const { return m_running; }

    void setMouseCallback(MouseCallback cb) { m_mouseCallback = cb; }
    void setKeyboardCallback(KeyboardCallback cb) { m_keyboardCallback = cb; }
    
    // Optimizations
    void setListenToMove(bool enable) { m_listenToMove = enable; }
    bool getModifierState(int vkCode);

private:
    static LRESULT CALLBACK MouseProc(int nCode, WPARAM wParam, LPARAM lParam);
    static LRESULT CALLBACK KeyboardProc(int nCode, WPARAM wParam, LPARAM lParam);

    void messageLoop();

    std::atomic<bool> m_running{false};
    std::atomic<bool> m_listenToMove{false};
    std::thread m_hookThread;
    
    HHOOK m_mouseHook{NULL};
    HHOOK m_keyboardHook{NULL};
    DWORD m_threadId{0};

    MouseCallback m_mouseCallback;
    KeyboardCallback m_keyboardCallback;

    // Singleton-ish instance for static callbacks
    static InputHook* s_instance;
    
    // Modifier state cache
    std::atomic<bool> m_modifiers[256]{false};
};

} // namespace helxaid
