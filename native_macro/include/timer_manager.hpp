#pragma once
#include <Windows.h>
#include <atomic>
#include <cstdint>
#include <functional>
#include <thread>


namespace helxairo {

/**
 * HighPrecisionTimer - Achieves sub-millisecond timing accuracy.
 *
 * Uses QueryPerformanceCounter for measurement and spin-wait
 * for precise delays under 15ms (Windows scheduler resolution).
 */
class HighPrecisionTimer {
public:
  HighPrecisionTimer();

  /**
   * Get current time in microseconds since timer construction.
   * @return Microseconds elapsed
   */
  uint64_t nowMicros() const;

  /**
   * Get current time in milliseconds since timer construction.
   * @return Milliseconds elapsed (floating point for precision)
   */
  double nowMillis() const;

  /**
   * Precise delay using spin-wait for accuracy.
   * For delays <15ms, uses busy-wait. For larger delays, uses Sleep.
   * @param microseconds Duration to wait
   */
  void delayMicros(uint64_t microseconds);

  /**
   * Precise delay in milliseconds.
   * @param milliseconds Duration to wait
   */
  void delayMillis(double milliseconds);

  /**
   * Busy-wait until target time is reached.
   * @param targetMicros Target timestamp (from nowMicros())
   */
  void waitUntil(uint64_t targetMicros);

private:
  LARGE_INTEGER m_frequency;
  LARGE_INTEGER m_startTime;
};

/**
 * RepeatingTimer - Executes callback at specified interval.
 * Uses dedicated thread with high-precision timing.
 */
class RepeatingTimer {
public:
  using Callback = std::function<void()>;

  /**
   * Create a repeating timer.
   * @param cb Callback to execute on each tick
   * @param intervalMicros Interval between ticks in microseconds
   */
  RepeatingTimer(Callback cb, uint64_t intervalMicros);
  ~RepeatingTimer();

  // Non-copyable
  RepeatingTimer(const RepeatingTimer &) = delete;
  RepeatingTimer &operator=(const RepeatingTimer &) = delete;

  /**
   * Start the timer. Callback begins executing at specified interval.
   */
  void start();

  /**
   * Stop the timer. Blocks until thread finishes.
   */
  void stop();

  /**
   * Change the interval (takes effect on next tick).
   * @param intervalMicros New interval in microseconds
   */
  void setInterval(uint64_t intervalMicros);

  /**
   * Check if timer is currently running.
   * @return True if timer thread is active
   */
  bool isRunning() const { return m_running.load(); }

private:
  void timerThread();

  Callback m_callback;
  std::atomic<uint64_t> m_interval;
  std::atomic<bool> m_running{false};
  std::thread m_thread;
  HighPrecisionTimer m_timer;
};

} // namespace helxairo
