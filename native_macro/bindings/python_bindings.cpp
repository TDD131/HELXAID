/**
 * Python bindings for HELXAIRO Native Macro System
 *
 * Exposes C++ classes to Python via pybind11 for high-performance
 * macro execution while keeping the UI in Python/PyQt.
 */

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "hid_controller.hpp"
#include "input_hook.hpp"
#include "input_simulator.hpp"
#include "macro_engine.hpp"
#include "macros/base_macro.hpp"
#include "macros/toggle_macro.hpp"
#include "timer_manager.hpp"

namespace py = pybind11;
using namespace helxairo;

PYBIND11_MODULE(helxairo_native, m) {
  m.doc() = "HELXAIRO Native Macro System - High-performance C++ core for "
            "sub-millisecond input latency";

  // Version info
  m.attr("__version__") = "1.0.0";

  // ==================== ENUMS ====================

  py::enum_<MouseButton>(m, "MouseButton", "Mouse button identifiers")
      .value("Left", MouseButton::Left)
      .value("Right", MouseButton::Right)
      .value("Middle", MouseButton::Middle)
      .value("X1", MouseButton::X1)
      .value("X2", MouseButton::X2)
      .export_values();

  py::enum_<EventType>(m, "EventType", "Input event types")
      .value("MouseDown", EventType::MouseDown)
      .value("MouseUp", EventType::MouseUp)
      .value("MouseMove", EventType::MouseMove)
      .value("MouseScroll", EventType::MouseScroll)
      .value("KeyDown", EventType::KeyDown)
      .value("KeyUp", EventType::KeyUp)
      .export_values();

  py::enum_<ToggleMacro::ActionType>(m, "ActionType", "Macro action types")
      .value("MouseClick", ToggleMacro::ActionType::MouseClick)
      .value("KeyTap", ToggleMacro::ActionType::KeyTap)
      .export_values();

  // ==================== EVENT STRUCTS ====================

  py::class_<MouseEvent>(m, "MouseEvent", "Mouse input event data")
      .def_readonly("type", &MouseEvent::type)
      .def_readonly("button", &MouseEvent::button)
      .def_readonly("x", &MouseEvent::x)
      .def_readonly("y", &MouseEvent::y)
      .def_readonly("delta", &MouseEvent::delta)
      .def_readonly("timestamp", &MouseEvent::timestamp)
      .def_readonly("injected", &MouseEvent::injected);

  py::class_<KeyboardEvent>(m, "KeyboardEvent", "Keyboard input event data")
      .def_readonly("type", &KeyboardEvent::type)
      .def_readonly("vk_code", &KeyboardEvent::vkCode)
      .def_readonly("scan_code", &KeyboardEvent::scanCode)
      .def_readonly("timestamp", &KeyboardEvent::timestamp)
      .def_readonly("injected", &KeyboardEvent::injected);

  // ==================== INPUT SIMULATOR ====================

  py::class_<InputSimulator>(m, "InputSimulator",
                             "High-performance input simulation")
      .def(py::init<>())

      // Mouse
      .def("mouse_move", &InputSimulator::mouseMove, py::arg("x"), py::arg("y"),
           py::arg("absolute") = true, "Move mouse to position")
      .def("mouse_move_relative", &InputSimulator::mouseMoveRelative,
           py::arg("dx"), py::arg("dy"), "Move mouse by offset")
      .def("mouse_down", &InputSimulator::mouseDown, py::arg("button") = "left",
           "Press mouse button")
      .def("mouse_up", &InputSimulator::mouseUp, py::arg("button") = "left",
           "Release mouse button")
      .def("mouse_click", &InputSimulator::mouseClick,
           py::arg("button") = "left", py::arg("count") = 1,
           "Click mouse button")
      .def("mouse_scroll", &InputSimulator::mouseScroll, py::arg("delta"),
           py::arg("horizontal") = false, "Scroll mouse wheel")

      // Keyboard
      .def("key_down", &InputSimulator::keyDown, py::arg("key"),
           "Press key down")
      .def("key_up", &InputSimulator::keyUp, py::arg("key"), "Release key")
      .def("key_tap", &InputSimulator::keyTap, py::arg("key"),
           py::arg("hold_ms") = 0, "Press and release key")
      .def("key_combo", &InputSimulator::keyCombo, py::arg("keys"),
           py::arg("hold_ms") = 0, "Press key combination")
      .def("type_text", &InputSimulator::typeText, py::arg("text"),
           py::arg("interval_ms") = 0, "Type text string")

      // State
      .def("get_cursor_position", &InputSimulator::getCursorPosition,
           "Get current cursor (x, y) position")
      .def("is_key_pressed", &InputSimulator::isKeyPressed, py::arg("key"),
           "Check if key is pressed")
      .def("is_mouse_button_pressed", &InputSimulator::isMouseButtonPressed,
           py::arg("button") = "left", "Check if mouse button is pressed");

  // ==================== HIGH PRECISION TIMER ====================

  py::class_<HighPrecisionTimer>(m, "HighPrecisionTimer",
                                 "Sub-millisecond precision timer")
      .def(py::init<>())
      .def("now_micros", &HighPrecisionTimer::nowMicros,
           "Get current time in microseconds")
      .def("now_millis", &HighPrecisionTimer::nowMillis,
           "Get current time in milliseconds")
      .def("delay_micros", &HighPrecisionTimer::delayMicros,
           py::arg("microseconds"),
           "Precise delay in microseconds (busy-wait for <15ms)")
      .def("delay_millis", &HighPrecisionTimer::delayMillis,
           py::arg("milliseconds"), "Precise delay in milliseconds");

  // ==================== MACRO BINDING ====================

  py::class_<MacroBinding>(m, "MacroBinding", "Links a trigger to a macro")
      .def(py::init<>())
      .def_readwrite("macro_id", &MacroBinding::macroId)
      .def_readwrite("trigger_type", &MacroBinding::triggerType)
      .def_readwrite("trigger_value", &MacroBinding::triggerValue)
      .def_readwrite("event_type", &MacroBinding::eventType)
      .def_readwrite("layer", &MacroBinding::layer);

  // ==================== INPUT HOOK ====================

  py::class_<InputHook>(m, "InputHook", "Low-level Windows hook manager")
      .def(py::init<>())
      .def("start", &InputHook::start)
      .def("stop", &InputHook::stop)
      .def("is_running", &InputHook::isRunning)
      .def("set_mouse_callback", &InputHook::setMouseCallback)
      .def("set_keyboard_callback", &InputHook::setKeyboardCallback)
      .def("set_listen_to_move", &InputHook::setListenToMove)
      .def("suppress_button", &InputHook::suppressButton, py::arg("button"),
           py::arg("suppress") = true)
      .def("suppress_key", &InputHook::suppressKey, py::arg("vk_code"),
           py::arg("suppress") = true)
      .def("clear_suppressions", &InputHook::clearSuppressions)
      .def("is_modifier_held", &InputHook::isModifierHeld, py::arg("vk_code"))
      .def("get_modifier_mask", &InputHook::getModifierMask);

  // ==================== MACRO ENGINE ====================

  py::class_<MacroEngine>(m, "MacroEngine", "Central macro execution engine")
      .def(py::init<>())

      // Lifecycle
      .def("start", &MacroEngine::start, "Start the macro engine")
      .def("stop", &MacroEngine::stop, "Stop the macro engine")
      .def("is_running", &MacroEngine::isRunning, "Check if engine is running")

      // Registration
      .def("register_macro", &MacroEngine::registerMacro, py::arg("id"),
           py::arg("macro"), "Register a macro instance")
      .def("unregister_macro", &MacroEngine::unregisterMacro, py::arg("id"),
           "Unregister a macro")
      .def("add_binding", &MacroEngine::addBinding, py::arg("binding"),
           "Add a trigger binding")
      .def("remove_bindings", &MacroEngine::removeBindings, py::arg("macro_id"),
           "Remove all bindings for a macro")
      .def("clear_bindings", &MacroEngine::clearBindings, "Clear all bindings")

      // Layer
      .def("set_active_layer", &MacroEngine::setActiveLayer, py::arg("layer"),
           "Set active layer")
      .def("get_active_layer", &MacroEngine::getActiveLayer, "Get active layer")

      // Matching
      .def("check_match_mouse", &MacroEngine::checkMatchMouse, py::arg("event"),
           py::arg("layer"), "Check for mouse macro match")
      .def("check_match_keyboard", &MacroEngine::checkMatchKeyboard,
           py::arg("event"), py::arg("layer"), "Check for keyboard macro match")

      // Toggle
      .def("is_toggle_on", &MacroEngine::isToggleOn, py::arg("macro_id"),
           "Check if toggle macro is ON")
      .def("set_toggle_state", &MacroEngine::setToggleState,
           py::arg("macro_id"), py::arg("state"), "Set toggle state manually")

      // Execution
      .def("trigger_macro", &MacroEngine::triggerMacro, py::arg("macro_id"),
           "Trigger macro execution")
      .def("cancel_macro", &MacroEngine::cancelMacro, py::arg("macro_id"),
           "Cancel running macro")
      .def("cancel_all_macros", &MacroEngine::cancelAllMacros,
           "Cancel all running macros");

  // ==================== HID CONTROLLER ====================

  py::class_<HIDController>(m, "HIDController", "Native HID communication")
      .def(py::init<>())
      .def("connect", &HIDController::connect,
           py::call_guard<py::gil_scoped_release>())
      .def("disconnect", &HIDController::disconnect,
           py::call_guard<py::gil_scoped_release>())
      .def("is_connected", &HIDController::isConnected)
      .def("get_connection_type", &HIDController::getConnectionType,
           py::call_guard<py::gil_scoped_release>())
      .def("set_button_mapping", &HIDController::setButtonMapping,
           py::call_guard<py::gil_scoped_release>())
      .def("get_battery_level", &HIDController::getBatteryLevel,
           py::call_guard<py::gil_scoped_release>())
      .def("get_active_dpi_stage", &HIDController::getActiveDpiStage,
           py::call_guard<py::gil_scoped_release>())
      .def("set_dpi_stage_value", &HIDController::setDpiStageValue,
           py::call_guard<py::gil_scoped_release>())
      .def("set_current_dpi_stage", &HIDController::setCurrentDpiStage,
           py::call_guard<py::gil_scoped_release>())
      .def("set_dpi_stages_count", &HIDController::setDpiStagesCount,
           py::call_guard<py::gil_scoped_release>())
      .def("set_polling_rate", &HIDController::setPollingRate,
           py::call_guard<py::gil_scoped_release>())
      .def("set_lod", &HIDController::setLod,
           py::call_guard<py::gil_scoped_release>())
      .def("set_ripple", &HIDController::setRipple,
           py::call_guard<py::gil_scoped_release>())
      .def("set_angle_snapping", &HIDController::setAngleSnapping,
           py::call_guard<py::gil_scoped_release>())
      .def("set_motion_sync", &HIDController::setMotionSync,
           py::call_guard<py::gil_scoped_release>())
      .def("set_debounce_time", &HIDController::setDebounceTime,
           py::call_guard<py::gil_scoped_release>())
      .def("set_sensor_mode", &HIDController::setSensorMode,
           py::call_guard<py::gil_scoped_release>())
      .def("set_highest_performance", &HIDController::setHighestPerformance,
           py::call_guard<py::gil_scoped_release>())
      .def("set_performance_time", &HIDController::setPerformanceTime,
           py::call_guard<py::gil_scoped_release>())
      .def("set_dpi_color", &HIDController::setDpiColor,
           py::call_guard<py::gil_scoped_release>())
      .def("set_dpi_effect_mode", &HIDController::setDpiEffectMode,
           py::call_guard<py::gil_scoped_release>())
      .def("set_dpi_effect_brightness", &HIDController::setDpiEffectBrightness,
           py::call_guard<py::gil_scoped_release>())
      .def("set_dpi_effect_speed", &HIDController::setDpiEffectSpeed,
           py::call_guard<py::gil_scoped_release>());

  // ==================== TOGGLE MACRO ====================

  // RepeatAction struct
  py::class_<ToggleMacro::RepeatAction>(m, "RepeatAction",
                                        "Configuration for repeat action")
      .def(py::init<>())
      .def_readwrite("type", &ToggleMacro::RepeatAction::type)
      .def_readwrite("target", &ToggleMacro::RepeatAction::target)
      .def_readwrite("hold_ms", &ToggleMacro::RepeatAction::holdMs);

  py::class_<ToggleMacro, std::shared_ptr<ToggleMacro>>(
      m, "ToggleMacro", "Toggle macro for auto-clickers")
      .def(py::init<const std::string &, const std::string &>(), py::arg("id"),
           py::arg("name"))

      // Configuration
      .def("set_repeat_action", &ToggleMacro::setRepeatAction,
           py::arg("action"), "Set action to repeat while ON")
      .def("set_repeat_interval_micros", &ToggleMacro::setRepeatIntervalMicros,
           py::arg("microseconds"), "Set repeat interval in microseconds")
      .def("set_repeat_interval_ms", &ToggleMacro::setRepeatIntervalMs,
           py::arg("milliseconds"), "Set repeat interval in milliseconds")
      .def("get_repeat_interval_micros", &ToggleMacro::getRepeatIntervalMicros,
           "Get repeat interval in microseconds")
      .def("set_hold_key", &ToggleMacro::setHoldKey, py::arg("key"),
           "Set key to hold while ON")
      .def("set_hold_button", &ToggleMacro::setHoldButton, py::arg("button"),
           "Set button to hold while ON")

      // Properties
      .def("get_id", &ToggleMacro::getId)
      .def("get_name", &ToggleMacro::getName)
      .def("is_enabled", &ToggleMacro::isEnabled)
      .def("set_enabled", &ToggleMacro::setEnabled, py::arg("enabled"))
      .def("is_toggle", &ToggleMacro::isToggle)
      .def("cancel", &ToggleMacro::cancel);

  // ==================== UTILITY FUNCTIONS ====================

  m.def("get_timestamp", &InputHook::getTimestamp,
        "Get high-precision timestamp in microseconds");
}
