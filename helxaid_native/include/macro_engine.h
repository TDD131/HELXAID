/**
 * Native Macro Engine Header
 *
 * High-performance macro matching and execution logic in C++.
 */

#pragma once

#include "input_hook.h"
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>


namespace helxaid {

struct MacroBinding {
  std::string macroId;
  std::string triggerType; // "mouse", "keyboard"
  int triggerValue;        // vkCode or button ID
  std::string eventType;   // "down", "up"
  std::string layer;
};

class NativeMacroEngine {
public:
  NativeMacroEngine();
  ~NativeMacroEngine();

  void addBinding(const MacroBinding &binding);
  void clearBindings();

  // Check if an event matches a macro
  std::string checkMatch(const MouseEvent &ev, const std::string &activeLayer);
  std::string checkMatch(const KeyboardEvent &ev,
                         const std::string &activeLayer);

private:
  std::mutex m_mutex;

  // Binding maps for O(1) lookup
  // Key: triggerValue, Value: vector of potential bindings
  std::map<int, std::vector<MacroBinding>> m_mouseBindings;
  std::map<int, std::vector<MacroBinding>> m_keyboardBindings;
};

} // namespace helxaid
