#include "macros/toggle_macro.hpp"
#include "input_simulator.hpp"
#include "timer_manager.hpp"

namespace helxairo {

ToggleMacro::ToggleMacro(const std::string &id, const std::string &name)
    : BaseMacro(id, name) {
  m_isToggle = true;
}

void ToggleMacro::setRepeatAction(const RepeatAction &action) {
  m_repeatAction = action;
}

void ToggleMacro::setRepeatIntervalMicros(uint64_t microseconds) {
  m_repeatIntervalMicros = microseconds;
}

void ToggleMacro::setHoldKey(const std::string &key) { m_holdKey = key; }

void ToggleMacro::setHoldButton(const std::string &button) {
  m_holdButton = button;
}

void ToggleMacro::execute(ExecutionContext &ctx) {
  auto *sim = ctx.simulator;
  auto *timer = ctx.timer;

  // Hold key/button if specified
  if (!m_holdKey.empty()) {
    sim->keyDown(m_holdKey);
    m_needsRelease = true;
  }
  if (!m_holdButton.empty()) {
    sim->mouseDown(m_holdButton);
    m_needsRelease = true;
  }

  // Repeat action loop
  if (!m_repeatAction.target.empty()) {
    while (!ctx.isCancelled()) {
      uint64_t startTime = timer->nowMicros();

      // Execute action
      if (m_repeatAction.type == ActionType::MouseClick) {
        sim->mouseClick(m_repeatAction.target, 1);
      } else if (m_repeatAction.type == ActionType::KeyTap) {
        sim->keyTap(m_repeatAction.target, m_repeatAction.holdMs);
      }

      // High-precision interval timing
      uint64_t targetInterval = m_repeatIntervalMicros > 0 ? m_repeatIntervalMicros : 1000;
      uint64_t elapsed = timer->nowMicros() - startTime;
      if (elapsed < targetInterval) {
        if (targetInterval <= 15000) {
          uint64_t target = startTime + targetInterval;
          while (timer->nowMicros() < target && !ctx.isCancelled()) {
            #if defined(_MSC_VER) || defined(__x86_64__) || defined(_M_X64)
            YieldProcessor();
            #endif
          }
        } else {
          ctx.delay(targetInterval - elapsed);
        }
      }
    }
  } else {
    // No repeat action - just wait until cancelled
    while (!ctx.isCancelled()) {
      ctx.delay(100000); // 100ms
    }
  }

  // Release repeat action state if cancelled mid-stroke
  if (!m_repeatAction.target.empty()) {
    if (m_repeatAction.type == ActionType::MouseClick) {
      sim->mouseUp(m_repeatAction.target);
    } else if (m_repeatAction.type == ActionType::KeyTap) {
      sim->keyUp(m_repeatAction.target);
    }
  }

  // Release held inputs
  if (m_needsRelease) {
    if (!m_holdKey.empty()) {
      sim->keyUp(m_holdKey);
    }
    if (!m_holdButton.empty()) {
      sim->mouseUp(m_holdButton);
    }
    m_needsRelease = false;
  }
}

void ToggleMacro::cancel() {
  BaseMacro::cancel();
  // Note: actual release happens in execute() when it exits the loop
}

} // namespace helxairo
