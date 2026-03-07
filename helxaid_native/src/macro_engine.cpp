/**
 * Native Macro Engine Implementation
 *
 * Fast matching logic for macro triggers.
 */

#include "macro_engine.h"

namespace helxaid {

NativeMacroEngine::NativeMacroEngine() {}
NativeMacroEngine::~NativeMacroEngine() {}

void NativeMacroEngine::addBinding(const MacroBinding &binding) {
  std::lock_guard<std::mutex> lock(m_mutex);
  if (binding.triggerType == "mouse") {
    m_mouseBindings[binding.triggerValue].push_back(binding);
  } else if (binding.triggerType == "keyboard") {
    m_keyboardBindings[binding.triggerValue].push_back(binding);
  }
}

void NativeMacroEngine::clearBindings() {
  std::lock_guard<std::mutex> lock(m_mutex);
  m_mouseBindings.clear();
  m_keyboardBindings.clear();
}

std::string NativeMacroEngine::checkMatch(const MouseEvent &ev,
                                          const std::string &activeLayer) {
  if (ev.button == MouseButton::None || ev.isMove)
    return "";

  std::lock_guard<std::mutex> lock(m_mutex);
  auto it = m_mouseBindings.find(static_cast<int>(ev.button));
  if (it != m_mouseBindings.end()) {
    const std::string targetEvent = ev.isDown ? "down" : "up";
    for (const auto &b : it->second) {
      if (b.eventType == targetEvent && b.layer == activeLayer) {
        return b.macroId;
      }
    }
  }
  return "";
}

std::string NativeMacroEngine::checkMatch(const KeyboardEvent &ev,
                                          const std::string &activeLayer) {
  std::lock_guard<std::mutex> lock(m_mutex);
  auto it = m_keyboardBindings.find(ev.vkCode);
  if (it != m_keyboardBindings.end()) {
    const std::string targetEvent = ev.isDown ? "down" : "up";
    for (const auto &b : it->second) {
      if (b.eventType == targetEvent && b.layer == activeLayer) {
        return b.macroId;
      }
    }
  }
  return "";
}

} // namespace helxaid
