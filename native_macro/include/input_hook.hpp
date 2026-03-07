#pragma once
#include <Windows.h>
#include <atomic>
#include <cstdint>
#include <functional>
#include <mutex>
#include <thread>
#include <unordered_set>


namespace helxairo {

/**
 * Mouse button identifiers.
 */
enum class MouseButton { Left, Right, Middle, X1, X2 };

/**
 * Input event types.
 */
enum class EventType {
  MouseDown,
  MouseUp,
  MouseMove,
  MouseScroll,
  KeyDown,
  KeyUp
};

/**
 * MouseEvent - Mouse input event data.
 * Contains all information about a mouse event captured by hooks.
 */
struct MouseEvent {
  EventType type;
  MouseButton button;
  int x, y;           // Screen coordinates
  int delta;          // Scroll delta (positive = up/right)
  uint64_t timestamp; // High-precision timestamp (microseconds)
  bool injected;      // True if this was injected by us
};

/**
 * KeyboardEvent - Keyboard input event data.
 * Contains all information about a keyboard event captured by hooks.
 */
struct KeyboardEvent {
  EventType type;
  uint32_t vkCode;    // Virtual key code
  uint32_t scanCode;  // Hardware scan code
  uint64_t timestamp; // High-precision timestamp (microseconds)
  bool injected;      // True if this was injected by us
};

// Windows hook structures
struct POINT_STRUCT {
  LONG x;
  LONG y;
};

struct MSLLHOOKSTRUCT_STRUCT {
  POINT_STRUCT pt;
  DWORD mouseData;
  DWORD flags;
  DWORD time;
  ULONG_PTR dwExtraInfo;
};

struct KBDLLHOOKSTRUCT_STRUCT {
  DWORD vkCode;
  DWORD scanCode;
  DWORD flags;
  DWORD time;
  ULONG_PTR dwExtraInfo;
};

/**
 * InputHook - Low-level Windows hook manager.
 *
 * Uses SetWindowsHookEx with WH_MOUSE_LL and WH_KEYBOARD_LL
 * for absolute minimum latency input capture.
 *
 * Thread Safety: All callbacks are invoked from the hook thread.
 * Use synchronization primitives when accessing shared state.
 */
class InputHook {
public:
  using MouseCallback = std::function<bool(const MouseEvent &)>;
  using KeyboardCallback = std::function<bool(const KeyboardEvent &)>;

  InputHook();
  ~InputHook();

  // Non-copyable
  InputHook(const InputHook &) = delete;
  InputHook &operator=(const InputHook &) = delete;

  // Start/stop hook processing
  void start();
  void stop();
  bool isRunning() const { return m_running.load(); }

  // Set callbacks (return true to suppress the event)
  void setMouseCallback(MouseCallback cb);
  void setKeyboardCallback(KeyboardCallback cb);
  void setListenToMove(bool enable) { m_listenToMove.store(enable); }

  // Suppression management
  void suppressButton(MouseButton button, bool suppress = true);
  void suppressKey(uint32_t vkCode, bool suppress = true);
  void clearSuppressions();

  // Modifier state query (Ctrl, Shift, Alt, Win)
  bool isModifierHeld(uint32_t vkCode) const;
  uint32_t getModifierMask() const;

  // Get high-precision timestamp
  static uint64_t getTimestamp();

private:
  static LRESULT CALLBACK mouseProc(int nCode, WPARAM wParam, LPARAM lParam);
  static LRESULT CALLBACK keyboardProc(int nCode, WPARAM wParam, LPARAM lParam);

  void hookThread();
  bool processMouseEvent(WPARAM wParam, MSLLHOOKSTRUCT_STRUCT *data);
  bool processKeyboardEvent(WPARAM wParam, KBDLLHOOKSTRUCT_STRUCT *data);

  std::atomic<bool> m_running{false};
  std::thread m_thread;
  HHOOK m_mouseHook{nullptr};
  HHOOK m_keyboardHook{nullptr};
  DWORD m_threadId{0};

  MouseCallback m_mouseCallback;
  KeyboardCallback m_keyboardCallback;

  mutable std::mutex m_mutex;
  std::unordered_set<int> m_suppressedButtons;
  std::unordered_set<uint32_t> m_suppressedKeys;

  std::atomic<uint32_t> m_modifierMask{0};
  std::atomic<bool> m_listenToMove{false};

  // Performance counter frequency for timestamps
  static LARGE_INTEGER s_frequency;
  static bool s_frequencyInitialized;

  static InputHook *s_instance; // For static hook procs
};

} // namespace helxairo
