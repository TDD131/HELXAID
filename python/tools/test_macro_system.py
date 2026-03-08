"""
Macro System Test Script

Run this to verify the macro system is working correctly.
"""

import sys
import time

# Add parent directory to path
sys.path.insert(0, '.')

def test_input_listener():
    """Test low-level input hooks."""
    print("\n=== Testing Input Listener ===")
    print("Move mouse, click buttons, press keys. Press Ctrl+C to stop.\n")
    
    from macro_system.core.input_listener import InputListener, EventType
    
    listener = InputListener()
    
    def on_mouse(event):
        if event.type == EventType.MOUSE_DOWN:
            print(f"  Mouse DOWN: {event.button.value} at ({event.x}, {event.y})")
        elif event.type == EventType.MOUSE_UP:
            print(f"  Mouse UP: {event.button.value}")
        elif event.type == EventType.MOUSE_SCROLL:
            direction = "up" if event.delta > 0 else "down"
            print(f"  Scroll {direction}")
        return False  # Don't suppress
        
    def on_keyboard(event):
        if event.type == EventType.KEY_DOWN:
            print(f"  Key DOWN: {event.key_name} (code: {event.key_code})")
        return False
        
    listener.on_mouse_event = on_mouse
    listener.on_keyboard_event = on_keyboard
    
    listener.start()
    
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
        
    listener.stop()
    print("\nInput listener test complete!")


def test_input_simulator():
    """Test input simulation."""
    print("\n=== Testing Input Simulator ===")
    print("Will simulate: mouse move, click, and keypress in 3 seconds...")
    
    from macro_system.core.input_simulator import InputSimulator
    
    sim = InputSimulator()
    
    time.sleep(3)
    
    # Get current position
    x, y = sim.get_cursor_position()
    print(f"  Current cursor: ({x}, {y})")
    
    # Move mouse
    print("  Moving mouse...")
    sim.mouse_move_relative(50, 0)
    time.sleep(0.3)
    sim.mouse_move_relative(-50, 0)
    
    # Simulate key
    print("  Pressing 'a' key...")
    sim.key_tap('a')
    
    print("\nInput simulator test complete!")


def test_auto_clicker():
    """Test toggle macro with auto-clicker."""
    print("\n=== Testing Auto-Clicker (Toggle Macro) ===")
    print("Press F6 to toggle auto-clicker ON/OFF. Press Ctrl+C to exit.\n")
    
    from macro_system import LauncherBridge
    
    bridge = LauncherBridge()
    bridge.start()
    
    # Create auto-clicker: F6 toggles, 200ms interval
    macro_id = bridge.create_quick_autoclicker("left", 200, "f6")
    print(f"  Created auto-clicker macro: {macro_id}")
    print("  Press F6 to toggle!")
    
    try:
        while True:
            is_on = bridge.engine.is_toggle_on(macro_id) if bridge.engine else False
            status = "ON" if is_on else "OFF"
            print(f"\r  Auto-clicker: {status}   ", end="", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
        
    bridge.shutdown()
    print("\n\nAuto-clicker test complete!")


def test_button_remap():
    """Test button remapping."""
    print("\n=== Testing Button Remap ===")
    print("Mouse X1 button will be remapped to 'Ctrl' key.")
    print("Try holding X1 and pressing another key. Press Ctrl+C to exit.\n")
    
    from macro_system import LauncherBridge
    
    bridge = LauncherBridge()
    bridge.start()
    
    # Remap X1 to Ctrl
    macro_id = bridge.create_quick_remap("x1", "ctrl")
    print(f"  Created remap macro: {macro_id}")
    print("  Hold X1 button - it should act as Ctrl!")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
        
    bridge.shutdown()
    print("\nButton remap test complete!")


def main():
    print("=" * 50)
    print("  HELXAID - Macro System Test Suite")
    print("=" * 50)
    
    print("\nSelect a test:")
    print("  1. Input Listener (see all inputs)")
    print("  2. Input Simulator (test output)")
    print("  3. Auto-Clicker (toggle macro)")
    print("  4. Button Remap (X1 → Ctrl)")
    print("  5. Run all tests")
    print("  0. Exit")
    
    choice = input("\nEnter choice: ").strip()
    
    if choice == "1":
        test_input_listener()
    elif choice == "2":
        test_input_simulator()
    elif choice == "3":
        test_auto_clicker()
    elif choice == "4":
        test_button_remap()
    elif choice == "5":
        test_input_simulator()
        test_auto_clicker()
    elif choice == "0":
        print("Bye!")
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
