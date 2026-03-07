#pragma once
#include "input_hook.hpp"
#include "input_simulator.hpp"
#include "timer_manager.hpp"
#include <atomic>
#include <condition_variable>
#include <functional>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

namespace helxairo {

// Forward declarations
class BaseMacro;

/**
 * MacroBinding - Links a trigger to a macro.
 */
struct MacroBinding {
  std::string macroId;
  std::string triggerType; // "mouse", "keyboard"
  uint32_t triggerValue;   // Button enum or VK code
  std::string eventType;   // "down", "up"
  std::string layer{"default"};
};

/**
 * MacroEngine - Central coordinator for macro execution.
 *
 * Responsibilities:
 * - Route input events to appropriate macros
 * - Manage macro execution lifecycle
 * - Handle toggle states
 * - Coordinate with layer system
 *
 * Thread Safety: Thread-safe for all public methods.
 */
class MacroEngine {
public:
  MacroEngine();
  ~MacroEngine();

  // Non-copyable
  MacroEngine(const MacroEngine &) = delete;
  MacroEngine &operator=(const MacroEngine &) = delete;

  // ==================== LIFECYCLE ====================

  /**
   * Start the macro engine. Installs hooks and begins processing.
   */
  void start();

  /**
   * Stop the macro engine. Cancels all macros and removes hooks.
   */
  void stop();

  /**
   * Check if engine is currently running.
   * @return True if started and active
   */
  bool isRunning() const { return m_running.load(); }

  // ==================== MACRO REGISTRATION ====================

  /**
   * Register a macro instance.
   * @param id Unique identifier
   * @param macro Shared pointer to macro object
   */
  void registerMacro(const std::string &id, std::shared_ptr<BaseMacro> macro);

  /**
   * Unregister a macro. Cancels if running.
   * @param id Macro identifier
   */
  void unregisterMacro(const std::string &id);

  /**
   * Add a trigger binding for a macro.
   * @param binding Binding configuration
   */
  void addBinding(const MacroBinding &binding);

  /**
   * Remove all bindings for a specific macro.
   * @param macroId Macro identifier
   */
  void removeBindings(const std::string &macroId);

  /**
   * Clear all bindings.
   */
  void clearBindings();

  // ==================== LAYER MANAGEMENT ====================

  /**
   * Set the active layer for macro lookups.
   * @param layer Layer name
   */
  void setActiveLayer(const std::string &layer);

  /**
   * Get current active layer.
   * @return Layer name
   */
  std::string getActiveLayer() const;
  // ==================== MATCHING ENGINE ====================

  /**
   * Check for a macro match from a mouse event.
   * @param event The mouse event
   * @param layer The active layer
   * @return Macro ID if matched, empty string otherwise
   */
  std::string checkMatchMouse(const MouseEvent &event,
                              const std::string &layer);

  /**
   * Check for a macro match from a keyboard event.
   * @param event The keyboard event
   * @param layer The active layer
   * @return Macro ID if matched, empty string otherwise
   */
  std::string checkMatchKeyboard(const KeyboardEvent &event,
                                 const std::string &layer);

  // ==================== TOGGLE STATE ====================

  /**
   * Check if a toggle macro is currently ON.
   * @param macroId Macro identifier
   * @return True if toggle is active
   */
  bool isToggleOn(const std::string &macroId) const;

  /**
   * Manually set toggle state.
   * @param macroId Macro identifier
   * @param state New state
   */
  void setToggleState(const std::string &macroId, bool state);

  // ==================== EXECUTION CONTROL ====================

  /**
   * Trigger a macro execution.
   * @param macroId Macro identifier
   */
  void triggerMacro(const std::string &macroId);

  /**
   * Cancel a running macro.
   * @param macroId Macro identifier
   */
  void cancelMacro(const std::string &macroId);

  /**
   * Cancel all running macros.
   */
  void cancelAllMacros();

  // ==================== SUBSYSTEM ACCESS ====================

  /**
   * Get reference to input simulator.
   * @return InputSimulator reference
   */
  InputSimulator &getSimulator() { return m_simulator; }

  /**
   * Get reference to high-precision timer.
   * @return HighPrecisionTimer reference
   */
  HighPrecisionTimer &getTimer() { return m_timer; }

private:
  // Input event handlers (called from hook thread)
  bool handleMouseEvent(const MouseEvent &event);
  bool handleKeyboardEvent(const KeyboardEvent &event);

  // Macro execution (runs in worker thread)
  void executionThread();
  void queueExecution(const std::string &macroId);
  void executeMacro(const std::string &macroId);

  // State
  std::atomic<bool> m_running{false};

  // Core components
  InputHook m_hook;
  InputSimulator m_simulator;
  HighPrecisionTimer m_timer;

  // Macro registry
  std::unordered_map<std::string, std::shared_ptr<BaseMacro>> m_macros;
  std::vector<MacroBinding> m_bindings;
  std::unordered_map<std::string, bool> m_toggleStates;
  std::unordered_map<std::string, std::atomic<bool> *> m_cancellationFlags;

  // Layer system
  std::string m_activeLayer{"default"};

  // Thread sync
  mutable std::mutex m_mutex;

  // Execution queue
  std::queue<std::string> m_executionQueue;
  std::mutex m_queueMutex;
  std::condition_variable m_queueCv;
  std::thread m_executionThread;
  std::atomic<bool> m_executionThreadRunning{false};
};

} // namespace helxairo
