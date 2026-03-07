#include "macro_engine.hpp"
#include "macros/base_macro.hpp"
#include <algorithm>
#include <iostream>

namespace helxairo {

MacroEngine::MacroEngine() {
  // Set up input callbacks
  m_hook.setMouseCallback(
      [this](const MouseEvent &e) { return handleMouseEvent(e); });

  m_hook.setKeyboardCallback(
      [this](const KeyboardEvent &e) { return handleKeyboardEvent(e); });
}

MacroEngine::~MacroEngine() { stop(); }

void MacroEngine::start() {
  if (m_running.load())
    return;

  m_running.store(true);

  // Start execution thread
  m_executionThreadRunning.store(true);
  m_executionThread = std::thread(&MacroEngine::executionThread, this);

  // Start input hooks
  m_hook.start();

  std::cout << "[MacroEngine] Started" << std::endl;
}

void MacroEngine::stop() {
  if (!m_running.load())
    return;

  m_running.store(false);

  // Cancel all macros
  cancelAllMacros();

  // Stop hooks
  m_hook.stop();

  // Stop execution thread
  m_executionThreadRunning.store(false);
  m_queueCv.notify_all();

  if (m_executionThread.joinable()) {
    m_executionThread.join();
  }

  std::cout << "[MacroEngine] Stopped" << std::endl;
}

void MacroEngine::registerMacro(const std::string &id,
                                std::shared_ptr<BaseMacro> macro) {
  std::lock_guard<std::mutex> lock(m_mutex);
  m_macros[id] = macro;
  m_toggleStates[id] = false;
}

void MacroEngine::unregisterMacro(const std::string &id) {
  cancelMacro(id);

  std::lock_guard<std::mutex> lock(m_mutex);
  m_macros.erase(id);
  m_toggleStates.erase(id);
  removeBindings(id);
}

void MacroEngine::addBinding(const MacroBinding &binding) {
  std::lock_guard<std::mutex> lock(m_mutex);
  m_bindings.push_back(binding);
}

void MacroEngine::removeBindings(const std::string &macroId) {
  std::lock_guard<std::mutex> lock(m_mutex);
  m_bindings.erase(std::remove_if(m_bindings.begin(), m_bindings.end(),
                                  [&macroId](const MacroBinding &b) {
                                    return b.macroId == macroId;
                                  }),
                   m_bindings.end());
}

void MacroEngine::clearBindings() {
  std::lock_guard<std::mutex> lock(m_mutex);
  m_bindings.clear();
}

void MacroEngine::setActiveLayer(const std::string &layer) {
  std::lock_guard<std::mutex> lock(m_mutex);
  m_activeLayer = layer;
}

std::string MacroEngine::getActiveLayer() const {
  std::lock_guard<std::mutex> lock(m_mutex);
  return m_activeLayer;
}

bool MacroEngine::isToggleOn(const std::string &macroId) const {
  std::lock_guard<std::mutex> lock(m_mutex);
  auto it = m_toggleStates.find(macroId);
  if (it != m_toggleStates.end()) {
    return it->second;
  }
  return false;
}

void MacroEngine::setToggleState(const std::string &macroId, bool state) {
  std::lock_guard<std::mutex> lock(m_mutex);
  m_toggleStates[macroId] = state;
}

void MacroEngine::triggerMacro(const std::string &macroId) {
  queueExecution(macroId);
}

void MacroEngine::cancelMacro(const std::string &macroId) {
  std::lock_guard<std::mutex> lock(m_mutex);

  auto it = m_macros.find(macroId);
  if (it != m_macros.end() && it->second) {
    it->second->cancel();
  }

  m_toggleStates[macroId] = false;
}

void MacroEngine::cancelAllMacros() {
  std::lock_guard<std::mutex> lock(m_mutex);

  for (auto &[id, macro] : m_macros) {
    if (macro) {
      macro->cancel();
    }
  }

  for (auto &[id, state] : m_toggleStates) {
    state = false;
  }
}

std::string MacroEngine::checkMatchMouse(const MouseEvent &event,
                                         const std::string &layer) {
  std::lock_guard<std::mutex> lock(m_mutex);

  for (const auto &binding : m_bindings) {
    if (binding.triggerType != "mouse")
      continue;
    if (binding.layer != layer && binding.layer != "*")
      continue;

    // Check button match
    int buttonInt = static_cast<int>(event.button);
    if (static_cast<uint32_t>(buttonInt) != binding.triggerValue)
      continue;

    // Check event type
    bool isDown = (event.type == EventType::MouseDown);
    bool isUp = (event.type == EventType::MouseUp);

    if (binding.eventType == "down" && !isDown)
      continue;
    if (binding.eventType == "up" && !isUp)
      continue;

    return binding.macroId;
  }

  return "";
}

std::string MacroEngine::checkMatchKeyboard(const KeyboardEvent &event,
                                            const std::string &layer) {
  std::lock_guard<std::mutex> lock(m_mutex);

  for (const auto &binding : m_bindings) {
    if (binding.triggerType != "keyboard")
      continue;
    if (binding.layer != layer && binding.layer != "*")
      continue;

    // Check key match
    if (event.vkCode != binding.triggerValue)
      continue;

    // Check event type
    bool isDown = (event.type == EventType::KeyDown);
    bool isUp = (event.type == EventType::KeyUp);

    if (binding.eventType == "down" && !isDown)
      continue;
    if (binding.eventType == "up" && !isUp)
      continue;

    return binding.macroId;
  }

  return "";
}

bool MacroEngine::handleMouseEvent(const MouseEvent &event) {
  if (!m_running.load())
    return false;
  if (event.injected)
    return false; // Ignore our own events

  std::string macroId = checkMatchMouse(event, m_activeLayer);
  if (macroId.empty())
    return false;

  std::lock_guard<std::mutex> lock(m_mutex);
  auto macroIt = m_macros.find(macroId);
  if (macroIt != m_macros.end() && macroIt->second) {
    auto &macro = macroIt->second;

    if (macro->isToggle()) {
      bool currentState = m_toggleStates[macroId];
      if (!currentState) {
        m_toggleStates[macroId] = true;
        macro->resetCancellation();
        queueExecution(macroId);
      } else {
        m_toggleStates[macroId] = false;
        macro->cancel();
      }
    } else {
      macro->resetCancellation();
      queueExecution(macroId);
    }
    return true;
  }

  return false;
}

bool MacroEngine::handleKeyboardEvent(const KeyboardEvent &event) {
  if (!m_running.load())
    return false;
  if (event.injected)
    return false;

  std::string macroId = checkMatchKeyboard(event, m_activeLayer);
  if (macroId.empty())
    return false;

  std::lock_guard<std::mutex> lock(m_mutex);
  auto macroIt = m_macros.find(macroId);
  if (macroIt != m_macros.end() && macroIt->second) {
    auto &macro = macroIt->second;

    if (macro->isToggle()) {
      bool currentState = m_toggleStates[macroId];
      if (!currentState) {
        m_toggleStates[macroId] = true;
        macro->resetCancellation();
        queueExecution(macroId);
      } else {
        m_toggleStates[macroId] = false;
        macro->cancel();
      }
    } else {
      macro->resetCancellation();
      queueExecution(macroId);
    }
    return true;
  }

  return false;
}

void MacroEngine::queueExecution(const std::string &macroId) {
  {
    std::lock_guard<std::mutex> lock(m_queueMutex);
    m_executionQueue.push(macroId);
  }
  m_queueCv.notify_one();
}

void MacroEngine::executionThread() {
  while (m_executionThreadRunning.load()) {
    std::string macroId;

    {
      std::unique_lock<std::mutex> lock(m_queueMutex);
      m_queueCv.wait(lock, [this] {
        return !m_executionQueue.empty() || !m_executionThreadRunning.load();
      });

      if (!m_executionThreadRunning.load() && m_executionQueue.empty()) {
        break;
      }

      if (!m_executionQueue.empty()) {
        macroId = m_executionQueue.front();
        m_executionQueue.pop();
      }
    }

    if (!macroId.empty()) {
      executeMacro(macroId);
    }
  }
}

void MacroEngine::executeMacro(const std::string &macroId) {
  std::shared_ptr<BaseMacro> macro;

  {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto it = m_macros.find(macroId);
    if (it == m_macros.end() || !it->second) {
      return;
    }
    macro = it->second;
  }

  if (!macro->isEnabled())
    return;

  // Create execution context
  ExecutionContext ctx;
  ctx.engine = this;
  ctx.simulator = &m_simulator;
  ctx.timer = &m_timer;
  ctx.cancelled = macro->getCancellationFlag();

  try {
    macro->execute(ctx);
  } catch (const std::exception &e) {
    std::cerr << "[MacroEngine] Macro " << macroId << " error: " << e.what()
              << std::endl;
  }
}

} // namespace helxairo
