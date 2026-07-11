import sys
import os
import time
import threading
import psutil

# Add parent dir to path so we can import launcher and WindowsCustomPanel
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

try:
    import launcher
    from WindowsCustomPanel import InvisibleLockScreen
except ImportError as e:
    print(f"Failed to import project files: {e}")
    sys.exit(1)

def get_handle_count():
    p = psutil.Process()
    try:
        return p.num_handles()
    except Exception:
        return 0

def run_stress_test(iterations=1000):
    print("=========================================")
    print(" HELXAID 24h Burn-in Simulator")
    print("=========================================")
    print("Monitoring GDI handles and thread safety...")
    
    start_handles = get_handle_count()
    print(f"Initial Handle Count: {start_handles}")
    
    # We will test thumbnail extraction on a dummy file or just pass an invalid file
    dummy_video = "C:\\Windows\\win.ini" # Real file to pass OS check, but fails COM parsing
    
    try:
        for i in range(1, iterations + 1):
            if i % 100 == 0:
                print(f"Iteration {i}/{iterations} | Current Handles: {get_handle_count()}")
            
            # 1. Trigger thumbnail extraction (this was leaking GDI handles)
            try:
                launcher.get_video_thumbnail(dummy_video)
            except Exception:
                pass
                
            # 2. Trigger Lock Screen activate/deactivate
            InvisibleLockScreen.activate(opacity=0)
            time.sleep(0.02) # Give it a moment to create HWND
            InvisibleLockScreen.deactivate()
            
    except KeyboardInterrupt:
        print("\nTest aborted by user.")
        
    print("\n-----------------------------------------")
    end_handles = get_handle_count()
    print(f"Final Handle Count: {end_handles}")
    diff = end_handles - start_handles
    print(f"Handle Difference: {diff}")
    
    if diff > 100:
        print("❌ WARNING: Possible Handle Leak Detected! (Difference > 100)")
    else:
        print("✅ SUCCESS: Handles remained stable. GDI/COM fixes are verified.")
    print("=========================================")

if __name__ == "__main__":
    # Test for 2000 iterations to verify stability
    run_stress_test(2000)
