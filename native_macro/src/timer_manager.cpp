#include "timer_manager.hpp"
#include <iostream>

namespace helxairo {

// Threshold for using busy-wait vs Sleep (Windows timer resolution)
constexpr uint64_t BUSY_WAIT_THRESHOLD_MICROS = 15000; // 15ms

HighPrecisionTimer::HighPrecisionTimer() {
  QueryPerformanceFrequency(&m_frequency);
  QueryPerformanceCounter(&m_startTime);
}

uint64_t HighPrecisionTimer::nowMicros() const {
  LARGE_INTEGER now;
  QueryPerformanceCounter(&now);
  return static_cast<uint64_t>((now.QuadPart - m_startTime.QuadPart) * 1000000 /
                               m_frequency.QuadPart);
}

double HighPrecisionTimer::nowMillis() const {
  return static_cast<double>(nowMicros()) / 1000.0;
}

void HighPrecisionTimer::delayMicros(uint64_t microseconds) {
  if (microseconds == 0)
    return;

  if (microseconds <= BUSY_WAIT_THRESHOLD_MICROS) {
    // Busy-wait for sub-15ms precision
    uint64_t target = nowMicros() + microseconds;
    while (nowMicros() < target) {
      // Spin
    }
  } else {
    // Use Sleep for large delays, with busy-wait for final portion
    uint64_t sleepMs = (microseconds - BUSY_WAIT_THRESHOLD_MICROS) / 1000;
    if (sleepMs > 0) {
      Sleep(static_cast<DWORD>(sleepMs));
    }

    // Busy-wait for remaining time
    uint64_t target = nowMicros() + (microseconds - sleepMs * 1000);
    while (nowMicros() < target) {
      // Spin
    }
  }
}

void HighPrecisionTimer::delayMillis(double milliseconds) {
  delayMicros(static_cast<uint64_t>(milliseconds * 1000));
}

void HighPrecisionTimer::waitUntil(uint64_t targetMicros) {
  uint64_t now = nowMicros();
  if (now >= targetMicros)
    return;

  uint64_t remaining = targetMicros - now;
  delayMicros(remaining);
}

// ==================== RepeatingTimer ====================

RepeatingTimer::RepeatingTimer(Callback cb, uint64_t intervalMicros)
    : m_callback(std::move(cb)), m_interval(intervalMicros) {}

RepeatingTimer::~RepeatingTimer() { stop(); }

void RepeatingTimer::start() {
  if (m_running.load())
    return;

  m_running.store(true);
  m_thread = std::thread(&RepeatingTimer::timerThread, this);
}

void RepeatingTimer::stop() {
  if (!m_running.load())
    return;

  m_running.store(false);

  if (m_thread.joinable()) {
    m_thread.join();
  }
}

void RepeatingTimer::setInterval(uint64_t intervalMicros) {
  m_interval.store(intervalMicros);
}

void RepeatingTimer::timerThread() {
  while (m_running.load()) {
    uint64_t startTime = m_timer.nowMicros();

    // Execute callback
    if (m_callback) {
      try {
        m_callback();
      } catch (const std::exception &e) {
        std::cerr << "[RepeatingTimer] Callback error: " << e.what()
                  << std::endl;
      }
    }

    // Calculate remaining time in interval
    uint64_t elapsed = m_timer.nowMicros() - startTime;
    uint64_t interval = m_interval.load();

    if (elapsed < interval) {
      m_timer.delayMicros(interval - elapsed);
    }
  }
}

} // namespace helxairo
