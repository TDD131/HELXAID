#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shobjidl.h>
#include <shellapi.h>
#include <commctrl.h>
#include <pybind11/pybind11.h>
#include <iostream>
#include <vector>
#include <string>
#include <unordered_set>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "comctl32.lib")

namespace py = pybind11;

class TaskbarManager {
private:
    ITaskbarList3* pTaskbar = nullptr;
    std::unordered_set<HWND> registered_hwnds;
    bool com_initialized = false;

public:
    TaskbarManager() {
        init();
    }

    ~TaskbarManager() {
        release();
    }

    bool init() {
        if (pTaskbar) {
            return true;
        }

        HRESULT hr_co = CoInitialize(NULL);
        if (SUCCEEDED(hr_co) || hr_co == S_FALSE || hr_co == RPC_E_CHANGED_MODE) {
            com_initialized = true;
        }

        HRESULT hr = CoCreateInstance(
            CLSID_TaskbarList,
            NULL,
            CLSCTX_INPROC_SERVER,
            IID_ITaskbarList3,
            (void**)&pTaskbar
        );

        if (SUCCEEDED(hr) && pTaskbar) {
            pTaskbar->HrInit();
            return true;
        }

        pTaskbar = nullptr;
        return false;
    }

    void release() {
        if (pTaskbar) {
            pTaskbar->Release();
            pTaskbar = nullptr;
        }
        registered_hwnds.clear();
    }

    bool is_available() const {
        return pTaskbar != nullptr;
    }

    bool reset() {
        // Release stale COM pointer (e.g. after Explorer restarts) then re-initialize
        release();
        return init();
    }


    int add_buttons(uintptr_t hwnd_val, uintptr_t prev_ico, uintptr_t play_ico, uintptr_t pause_ico, uintptr_t next_ico, bool is_playing) {
        if (!pTaskbar && !init()) {
            return -1;
        }

        HWND hwnd = (HWND)hwnd_val;
        if (!hwnd || !IsWindow(hwnd)) {
            return -2;
        }

        THUMBBUTTON buttons[3] = {};

        // Button 0: Previous (ID 100)
        buttons[0].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS;
        buttons[0].iId = 100;
        buttons[0].iBitmap = 0;
        buttons[0].hIcon = (HICON)prev_ico;
        wcscpy_s(buttons[0].szTip, L"Previous");
        buttons[0].dwFlags = THBF_ENABLED;

        // Button 1: Play / Pause (ID 101)
        buttons[1].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS;
        buttons[1].iId = 101;
        buttons[1].iBitmap = 0;
        buttons[1].hIcon = (HICON)(is_playing ? pause_ico : play_ico);
        wcscpy_s(buttons[1].szTip, is_playing ? L"Pause" : L"Play");
        buttons[1].dwFlags = THBF_ENABLED;

        // Button 2: Next (ID 102)
        buttons[2].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS;
        buttons[2].iId = 102;
        buttons[2].iBitmap = 0;
        buttons[2].hIcon = (HICON)next_ico;
        wcscpy_s(buttons[2].szTip, L"Next");
        buttons[2].dwFlags = THBF_ENABLED;

        HRESULT hr = pTaskbar->ThumbBarAddButtons(hwnd, 3, buttons);
        if (SUCCEEDED(hr)) {
            registered_hwnds.insert(hwnd);
        }
        return (int)hr;
    }

    int update_play_state(uintptr_t hwnd_val, bool is_playing, uintptr_t play_ico, uintptr_t pause_ico) {
        if (!pTaskbar && !init()) {
            return -1;
        }

        HWND hwnd = (HWND)hwnd_val;
        if (!hwnd || !IsWindow(hwnd)) {
            return -2;
        }

        THUMBBUTTON btn = {};
        btn.dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS;
        btn.iId = 101;
        btn.iBitmap = 0;
        btn.hIcon = (HICON)(is_playing ? pause_ico : play_ico);
        wcscpy_s(btn.szTip, is_playing ? L"Pause" : L"Play");
        btn.dwFlags = THBF_ENABLED;

        HRESULT hr = pTaskbar->ThumbBarUpdateButtons(hwnd, 1, &btn);
        return (int)hr;
    }

    int set_buttons_visible(uintptr_t hwnd_val, bool visible, uintptr_t prev_ico, uintptr_t play_ico, uintptr_t pause_ico, uintptr_t next_ico, bool is_playing) {
        if (!pTaskbar && !init()) {
            return -1;
        }

        HWND hwnd = (HWND)hwnd_val;
        if (!hwnd || !IsWindow(hwnd)) {
            return -2;
        }

        THUMBBUTTONFLAGS flags = visible ? THBF_ENABLED : THBF_HIDDEN;
        THUMBBUTTON buttons[3] = {};

        // Button 0: Previous
        buttons[0].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS;
        buttons[0].iId = 100;
        buttons[0].iBitmap = 0;
        buttons[0].hIcon = (HICON)prev_ico;
        wcscpy_s(buttons[0].szTip, L"Previous");
        buttons[0].dwFlags = flags;

        // Button 1: Play/Pause
        buttons[1].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS;
        buttons[1].iId = 101;
        buttons[1].iBitmap = 0;
        buttons[1].hIcon = (HICON)(is_playing ? pause_ico : play_ico);
        wcscpy_s(buttons[1].szTip, is_playing ? L"Pause" : L"Play");
        buttons[1].dwFlags = flags;

        // Button 2: Next
        buttons[2].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS;
        buttons[2].iId = 102;
        buttons[2].iBitmap = 0;
        buttons[2].hIcon = (HICON)next_ico;
        wcscpy_s(buttons[2].szTip, L"Next");
        buttons[2].dwFlags = flags;

        HRESULT hr = pTaskbar->ThumbBarUpdateButtons(hwnd, 3, buttons);
        return (int)hr;
    }

    int set_progress(uintptr_t hwnd_val, uint64_t current_ms, uint64_t total_ms) {
        if (!pTaskbar && !init()) {
            return -1;
        }

        HWND hwnd = (HWND)hwnd_val;
        if (!hwnd || !IsWindow(hwnd)) {
            return -2;
        }

        if (total_ms > 0) {
            pTaskbar->SetProgressState(hwnd, TBPF_NORMAL);
            HRESULT hr = pTaskbar->SetProgressValue(hwnd, current_ms, total_ms);
            return (int)hr;
        } else {
            HRESULT hr = pTaskbar->SetProgressState(hwnd, TBPF_NOPROGRESS);
            return (int)hr;
        }
    }

    int set_progress_state(uintptr_t hwnd_val, int state) {
        if (!pTaskbar && !init()) {
            return -1;
        }

        HWND hwnd = (HWND)hwnd_val;
        if (!hwnd || !IsWindow(hwnd)) {
            return -2;
        }

        HRESULT hr = pTaskbar->SetProgressState(hwnd, (TBPFLAG)state);
        return (int)hr;
    }

    int set_overlay_icon(uintptr_t hwnd_val, uintptr_t hicon_val, const std::wstring& description) {
        if (!pTaskbar && !init()) {
            return -1;
        }

        HWND hwnd = (HWND)hwnd_val;
        if (!hwnd || !IsWindow(hwnd)) {
            return -2;
        }

        HRESULT hr = pTaskbar->SetOverlayIcon(hwnd, (HICON)hicon_val, description.empty() ? NULL : description.c_str());
        return (int)hr;
    }

    static uintptr_t create_icon_from_rgba(const py::bytes& raw_bytes, int width, int height) {
        std::string buffer = raw_bytes;
        if (buffer.size() < (size_t)(width * height * 4)) {
            return 0;
        }

        HDC hdcScreen = GetDC(NULL);
        HDC hdcMem = CreateCompatibleDC(hdcScreen);

        BITMAPINFO bmi = {};
        bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        bmi.bmiHeader.biWidth = width;
        bmi.bmiHeader.biHeight = -height; // Top-down DIB
        bmi.bmiHeader.biPlanes = 1;
        bmi.bmiHeader.biBitCount = 32;
        bmi.bmiHeader.biCompression = BI_RGB;

        void* pBits = nullptr;
        HBITMAP hbmColor = CreateDIBSection(hdcMem, &bmi, DIB_RGB_COLORS, &pBits, NULL, 0);
        if (!hbmColor || !pBits) {
            DeleteDC(hdcMem);
            ReleaseDC(NULL, hdcScreen);
            return 0;
        }

        // Convert RGBA to BGRA (native Windows DIB format)
        const uint8_t* src = reinterpret_cast<const uint8_t*>(buffer.data());
        uint8_t* dst = reinterpret_cast<uint8_t*>(pBits);
        for (int i = 0; i < width * height; ++i) {
            uint8_t r = src[i * 4 + 0];
            uint8_t g = src[i * 4 + 1];
            uint8_t b = src[i * 4 + 2];
            uint8_t a = src[i * 4 + 3];

            dst[i * 4 + 0] = b;
            dst[i * 4 + 1] = g;
            dst[i * 4 + 2] = r;
            dst[i * 4 + 3] = a;
        }

        // Create 1-bit monochrome mask bitmap
        HBITMAP hbmMask = CreateBitmap(width, height, 1, 1, NULL);

        ICONINFO iconInfo = {};
        iconInfo.fIcon = TRUE;
        iconInfo.xHotspot = 0;
        iconInfo.yHotspot = 0;
        iconInfo.hbmMask = hbmMask;
        iconInfo.hbmColor = hbmColor;

        HICON hIcon = CreateIconIndirect(&iconInfo);

        // Cleanup temporary GDI resources
        DeleteObject(hbmColor);
        DeleteObject(hbmMask);
        DeleteDC(hdcMem);
        ReleaseDC(NULL, hdcScreen);

        return (uintptr_t)hIcon;
    }

    static void destroy_icon(uintptr_t hicon_val) {
        if (hicon_val) {
            DestroyIcon((HICON)hicon_val);
        }
    }
};

PYBIND11_MODULE(taskbar_native, m) {
    m.doc() = "HELXAID Native C++ Windows Taskbar & Media Control Integration";

    py::class_<TaskbarManager>(m, "TaskbarManager")
        .def(py::init<>())
        .def("init", &TaskbarManager::init)
        .def("release", &TaskbarManager::release)
        .def("is_available", &TaskbarManager::is_available)
        .def("add_buttons", &TaskbarManager::add_buttons,
            py::arg("hwnd"), py::arg("prev_ico"), py::arg("play_ico"), py::arg("pause_ico"), py::arg("next_ico"), py::arg("is_playing") = false)
        .def("update_play_state", &TaskbarManager::update_play_state,
            py::arg("hwnd"), py::arg("is_playing"), py::arg("play_ico"), py::arg("pause_ico"))
        .def("set_buttons_visible", &TaskbarManager::set_buttons_visible,
            py::arg("hwnd"), py::arg("visible"), py::arg("prev_ico"), py::arg("play_ico"), py::arg("pause_ico"), py::arg("next_ico"), py::arg("is_playing") = false)
        .def("set_progress", &TaskbarManager::set_progress,
            py::arg("hwnd"), py::arg("current_ms"), py::arg("total_ms"))
        .def("set_progress_state", &TaskbarManager::set_progress_state,
            py::arg("hwnd"), py::arg("state"))
        .def("set_overlay_icon", &TaskbarManager::set_overlay_icon,
            py::arg("hwnd"), py::arg("hicon"), py::arg("description") = L"")
        .def("reset", &TaskbarManager::reset);

    m.def("create_icon_from_rgba", &TaskbarManager::create_icon_from_rgba,
        py::arg("raw_bytes"), py::arg("width"), py::arg("height"));
    m.def("destroy_icon", &TaskbarManager::destroy_icon,
        py::arg("hicon"));
}
