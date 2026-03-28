import sys
import ctypes
from ctypes import Structure, c_int, c_uint, c_wchar, POINTER, byref, windll, c_void_p, WINFUNCTYPE, HRESULT
from ctypes.wintypes import HWND, HICON, DWORD, UINT, BOOL
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import QTimer

# GUID structure
class GUID(Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8)
    ]

# THUMBBUTTON structure for Windows 7+ taskbar
class THUMBBUTTON(Structure):
    _fields_ = [
        ("dwMask", DWORD),
        ("iId", UINT),
        ("iBitmap", UINT),
        ("hIcon", HICON),
        ("szTip", c_wchar * 260),
        ("dwFlags", DWORD),
    ]

# Constants
THB_BITMAP = 0x1
THB_ICON = 0x2
THB_TOOLTIP = 0x4
THB_FLAGS = 0x8
THBF_ENABLED = 0x0

# GUIDs
CLSID_TaskbarList = GUID(0x56FDF344, 0xFD6D, 0x11d0, (ctypes.c_ubyte * 8)(0x95, 0x8A, 0x00, 0x60, 0x97, 0xC9, 0xA0, 0x90))
IID_ITaskbarList3 = GUID(0xEA1AFB91, 0x9E28, 0x4B86, (ctypes.c_ubyte * 8)(0x90, 0xE9, 0x9E, 0x9F, 0x8A, 0x5E, 0xEF, 0xAF))

CoCreateInstance = windll.ole32.CoCreateInstance
CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, DWORD, POINTER(GUID), POINTER(c_void_p)]
CoCreateInstance.restype = HRESULT

class TaskbarTestWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Taskbar Thumbnail Test")
        self.setFixedSize(300, 200)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Wait for 3 seconds..."))
        
        self.taskbar = None
        self.buttons_added = False
        
        self._init_taskbar()
        QTimer.singleShot(1000, self._add_buttons)
        QTimer.singleShot(5000, self.close)

    def _init_taskbar(self):
        print("[Taskbar DEBUG] Initializing COM CoInitialize...")
        try:
            windll.ole32.CoInitialize(None)
            taskbar_ptr = c_void_p()
            hr = CoCreateInstance(
                byref(CLSID_TaskbarList), None, 1, byref(IID_ITaskbarList3), byref(taskbar_ptr)
            )
            
            if hr != 0 or not taskbar_ptr:
                print(f"[Taskbar ERROR] CoCreateInstance failed: HRESULT {hex(hr & 0xFFFFFFFF)}")
                return
            
            self.taskbar = taskbar_ptr.value
            vtable = ctypes.cast(self.taskbar, POINTER(c_void_p)).contents
            vtable_ptr = ctypes.cast(vtable, POINTER(c_void_p * 30)).contents
            HrInit_proto = WINFUNCTYPE(HRESULT, c_void_p)
            HrInit = HrInit_proto(vtable_ptr[3])
            hr = HrInit(self.taskbar)
            if hr == 0:
                print("[Taskbar SUCCESS] ITaskbarList3 initialized completely")
            else:
                print(f"[Taskbar ERROR] HrInit failed: HRESULT {hex(hr & 0xFFFFFFFF)}")
        except Exception as e:
            print(f"[Taskbar FATAL] Explosion during ITaskbarList3 init: {e}")

    def _add_buttons(self):
        try:
            hwnd = int(self.winId())
            root_hwnd = windll.user32.GetAncestor(hwnd, 2) # GA_ROOT
            target_hwnd = root_hwnd if root_hwnd else hwnd
            print(f"Original HWND: {hwnd}, Target HWND: {target_hwnd}")

            # Extract an icon for testing
            shell32_path = r"C:\Windows\System32\shell32.dll"
            hicons_large = (HICON * 1)()
            hicons_small = (HICON * 1)()
            windll.shell32.ExtractIconExW(shell32_path, 131, hicons_large, hicons_small, 1)
            icon = hicons_small[0] if hicons_small[0] else 0

            buttons = (THUMBBUTTON * 1)()
            buttons[0].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
            buttons[0].iId = 100
            buttons[0].hIcon = icon
            buttons[0].szTip = "Test Button"
            buttons[0].dwFlags = THBF_ENABLED

            vtable = ctypes.cast(self.taskbar, POINTER(c_void_p)).contents
            vtable_ptr = ctypes.cast(vtable, POINTER(c_void_p * 30)).contents
            ThumbBarAddButtons_proto = WINFUNCTYPE(HRESULT, c_void_p, HWND, UINT, POINTER(THUMBBUTTON))
            ThumbBarAddButtons = ThumbBarAddButtons_proto(vtable_ptr[15])

            print(f"ThumbBarAddButtons is at {hex(vtable_ptr[15])}")
            hr = ThumbBarAddButtons(self.taskbar, target_hwnd, 1, buttons)

            if hr == 0:
                print("[Taskbar SUCCESS] Taskbar buttons added successfully")
            else:
                print(f"[Taskbar ERROR] ThumbBarAddButtons failed with HRESULT: {hex(hr & 0xFFFFFFFF)}")

            # Try allowing UIPI messages just in case
            WM_TASKBARBUTTONCREATED = windll.user32.RegisterWindowMessageW("TaskbarButtonCreated")
            windll.user32.ChangeWindowMessageFilterEx(target_hwnd, WM_TASKBARBUTTONCREATED, 1, None)
            windll.user32.ChangeWindowMessageFilterEx(target_hwnd, 0x0111, 1, None)

        except Exception as e:
            print(f"Error adding buttons: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = TaskbarTestWidget()
    w.show()
    sys.exit(app.exec())
