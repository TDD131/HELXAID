#include "macros/base_macro.hpp"
#include "timer_manager.hpp"
#include <algorithm>

namespace helxairo {

BaseMacro::BaseMacro(const std::string &id, const std::string &name)
    : m_id(id), m_name(name) {}

void BaseMacro::cancel() { m_cancelled.store(true); }

void BaseMacro::resetCancellation() { m_cancelled.store(false); }

// ExecutionContext implementation
void ExecutionContext::delay(uint64_t microseconds) {
  if (microseconds == 0)
    return;

  // Check for cancellation periodically during long delays
  constexpr uint64_t CHECK_INTERVAL = 10000; // Check every 10ms

  while (microseconds > 0 && !isCancelled()) {
    uint64_t sleepTime = std::min(microseconds, CHECK_INTERVAL);
    timer->delayMicros(sleepTime);
    microseconds -= sleepTime;
  }
}

} // namespace helxairo
