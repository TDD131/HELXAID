#pragma once
#include <atomic>
#include <cstdint>
#include <string>


namespace helxairo {

class MacroEngine;
class InputSimulator;
class HighPrecisionTimer;

/**
 * ExecutionContext - Passed to macros during execution.
 * Provides access to engine services and cancellation support.
 */
struct ExecutionContext {
  MacroEngine *engine;
  InputSimulator *simulator;
  HighPrecisionTimer *timer;
  std::atomic<bool> *cancelled;

  /**
   * Check if execution was cancelled.
   * @return True if cancel was requested
   */
  bool isCancelled() const { return cancelled && cancelled->load(); }

  /**
   * Delay with cancellation support.
   * Checks cancellation periodically during long delays.
   * @param microseconds Duration to wait
   */
  void delay(uint64_t microseconds);

  /**
   * Delay in milliseconds.
   * @param milliseconds Duration to wait
   */
  void delayMs(double milliseconds) {
    delay(static_cast<uint64_t>(milliseconds * 1000));
  }
};

/**
 * BaseMacro - Abstract base for all macro types.
 *
 * All macro implementations must inherit from this class
 * and implement the execute() method.
 */
class BaseMacro {
public:
  /**
   * Construct a macro.
   * @param id Unique identifier
   * @param name Display name
   */
  BaseMacro(const std::string &id, const std::string &name);

  virtual ~BaseMacro() = default;

  // Non-copyable
  BaseMacro(const BaseMacro &) = delete;
  BaseMacro &operator=(const BaseMacro &) = delete;

  /**
   * Execute the macro.
   * Called in dedicated execution thread.
   * @param ctx Execution context providing services
   */
  virtual void execute(ExecutionContext &ctx) = 0;

  /**
   * Request cancellation of execution.
   * Sets the cancelled flag checked by execute().
   */
  virtual void cancel();

  /**
   * Reset cancellation flag for next execution.
   */
  void resetCancellation();

  // ==================== PROPERTIES ====================

  const std::string &getId() const { return m_id; }
  const std::string &getName() const { return m_name; }

  bool isEnabled() const { return m_enabled.load(); }
  void setEnabled(bool enabled) { m_enabled.store(enabled); }

  bool isToggle() const { return m_isToggle; }

  std::atomic<bool> *getCancellationFlag() { return &m_cancelled; }

protected:
  std::string m_id;
  std::string m_name;
  std::atomic<bool> m_enabled{true};
  std::atomic<bool> m_cancelled{false};
  bool m_isToggle{false};
};

} // namespace helxairo
