#pragma once
#include "base_macro.hpp"
#include <string>

namespace helxairo {

/**
 * ToggleMacro - ON/OFF toggle behavior.
 *
 * While ON, can:
 * - Repeat an action at high-precision interval (auto-clicker)
 * - Hold a key/button down
 *
 * Toggle macros flip state on each trigger (hotkey press).
 */
class ToggleMacro : public BaseMacro {
public:
  /**
   * Action types that can be repeated.
   */
  enum class ActionType {
    MouseClick, // Click mouse button
    KeyTap      // Press and release key
  };

  /**
   * Configuration for repeat action.
   */
  struct RepeatAction {
    ActionType type;
    std::string target; // Button name or key name
    int holdMs{0};      // Hold duration for key taps
  };

  /**
   * Construct a toggle macro.
   * @param id Unique identifier
   * @param name Display name
   */
  ToggleMacro(const std::string &id, const std::string &name);

  /**
   * Set the action to repeat while toggled ON.
   * @param action Action configuration
   */
  void setRepeatAction(const RepeatAction &action);

  /**
   * Set repeat interval.
   * For best precision, use microseconds.
   * @param microseconds Interval between repeats
   */
  void setRepeatIntervalMicros(uint64_t microseconds);

  /**
   * Set repeat interval in milliseconds.
   * @param milliseconds Interval between repeats
   */
  void setRepeatIntervalMs(double milliseconds) {
    setRepeatIntervalMicros(static_cast<uint64_t>(milliseconds * 1000));
  }

  /**
   * Set a key to hold while toggled ON.
   * @param key Key name to hold
   */
  void setHoldKey(const std::string &key);

  /**
   * Set a mouse button to hold while toggled ON.
   * @param button Button name to hold
   */
  void setHoldButton(const std::string &button);

  /**
   * Get current repeat interval.
   * @return Interval in microseconds
   */
  uint64_t getRepeatIntervalMicros() const { return m_repeatIntervalMicros; }

  /**
   * Execute toggle behavior.
   * Runs until cancelled (toggle OFF or macro cancel).
   * @param ctx Execution context
   */
  void execute(ExecutionContext &ctx) override;

  /**
   * Cancel and release any held keys/buttons.
   */
  void cancel() override;

private:
  RepeatAction m_repeatAction;
  uint64_t m_repeatIntervalMicros{100000}; // 100ms default
  std::string m_holdKey;
  std::string m_holdButton;
  bool m_needsRelease{false}; // Track if we need to release held input
};

} // namespace helxairo
