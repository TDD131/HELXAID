/**
 * Icon Extractor Implementation
 *
 * Windows Shell API-based high-performance icon extraction.
 */

#include "icon_extractor.h"

#include <algorithm>
#include <future>
#include <mutex>
#include <thread>

#ifdef _WIN32
#include <comdef.h>
#include <commctrl.h>
#include <commoncontrols.h>
#include <shellapi.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <shobjidl.h>

#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "comctl32.lib")
#endif

namespace helxaid {

// PIMPL implementation details
struct IconExtractor::Impl {
  bool comInitialized = false;
  std::mutex mutex;
};

IconExtractor::IconExtractor() : pImpl(std::make_unique<Impl>()) {
#ifdef _WIN32
  HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
  pImpl->comInitialized = SUCCEEDED(hr) || hr == RPC_E_CHANGED_MODE;
#endif
}

IconExtractor::~IconExtractor() {
#ifdef _WIN32
  // Don't uninitialize COM here as other parts might use it
#endif
}

IconExtractor::IconExtractor(IconExtractor &&other) noexcept = default;
IconExtractor &
IconExtractor::operator=(IconExtractor &&other) noexcept = default;

#ifdef _WIN32
// Convert UTF-8 string to wide string
static std::wstring utf8ToWide(const std::string &str) {
  if (str.empty())
    return std::wstring();
  int size = MultiByteToWideChar(CP_UTF8, 0, str.c_str(), -1, nullptr, 0);
  std::wstring result(size - 1, 0);
  MultiByteToWideChar(CP_UTF8, 0, str.c_str(), -1, &result[0], size);
  return result;
}

// Convert wide string to UTF-8
static std::string wideToUtf8(const std::wstring &wstr) {
  if (wstr.empty())
    return std::string();
  int size = WideCharToMultiByte(CP_UTF8, 0, wstr.c_str(), -1, nullptr, 0,
                                 nullptr, nullptr);
  std::string result(size - 1, 0);
  WideCharToMultiByte(CP_UTF8, 0, wstr.c_str(), -1, &result[0], size, nullptr,
                      nullptr);
  return result;
}
#endif

IconResult IconExtractor::extract(const std::string &path, int size) {
#ifdef _WIN32
  std::wstring wpath = utf8ToWide(path);
  IconResult bestResult = {.success = false,
                           .error = "No extraction method succeeded"};
  int bestSize = 0;

  // Method 1: Try IShellItemImageFactory (usually gets good quality)
  auto result = extractWithShellApi(wpath, size);
  if (result.success) {
    int currentSize = std::max(result.width, result.height);
    if (currentSize >= size || currentSize > bestSize) {
      if (currentSize >= 128) {
        return result; // Good enough, return immediately
      }
      if (currentSize > bestSize) {
        bestResult = std::move(result);
        bestSize = currentSize;
      }
    }
  }

  // Method 2: Try to get Jumbo icons (256x256) using SHGetImageList
  auto jumboResult = extractJumboIcon(wpath, size);
  if (jumboResult.success) {
    int currentSize = std::max(jumboResult.width, jumboResult.height);
    if (currentSize >= 128) {
      return jumboResult; // Good quality, return immediately
    }
    if (currentSize > bestSize) {
      bestResult = std::move(jumboResult);
      bestSize = currentSize;
    }
  }

  // For LNK files, resolve target and try again
  std::wstring ext = PathFindExtensionW(wpath.c_str());
  if (_wcsicmp(ext.c_str(), L".lnk") == 0) {
    result = extractFromLnk(wpath, size);
    if (result.success) {
      int currentSize = std::max(result.width, result.height);
      if (currentSize >= 128) {
        return result;
      }
      if (currentSize > bestSize) {
        bestResult = std::move(result);
        bestSize = currentSize;
      }
    }
  }

  // For EXE files, try ExtractIconEx as last resort
  if (_wcsicmp(ext.c_str(), L".exe") == 0) {
    result = extractFromExe(wpath, size);
    if (result.success) {
      int currentSize = std::max(result.width, result.height);
      if (currentSize > bestSize) {
        bestResult = std::move(result);
        bestSize = currentSize;
      }
    }
  }

  // Return best result we found (even if small)
  if (bestResult.success) {
    return bestResult;
  }

  return {.success = false,
          .error = "All extraction methods failed for: " + path};
#else
  return {.success = false,
          .error = "Icon extraction only supported on Windows"};
#endif
}

#ifdef _WIN32
IconResult IconExtractor::extractWithShellApi(const std::wstring &path,
                                              int size) {
  IShellItemImageFactory *pFactory = nullptr;

  HRESULT hr = SHCreateItemFromParsingName(path.c_str(), nullptr,
                                           IID_PPV_ARGS(&pFactory));

  if (FAILED(hr) || !pFactory) {
    return {.success = false, .error = "Failed to create shell item"};
  }

  HBITMAP hBitmap = nullptr;
  SIZE sz = {size, size};

  // Try to get high-quality image
  hr = pFactory->GetImage(sz, SIIGBF_RESIZETOFIT | SIIGBF_BIGGERSIZEOK,
                          &hBitmap);
  pFactory->Release();

  if (FAILED(hr) || !hBitmap) {
    return {.success = false, .error = "Failed to get image from shell item"};
  }

  // Get bitmap info
  BITMAP bm;
  if (GetObject(hBitmap, sizeof(bm), &bm) == 0) {
    DeleteObject(hBitmap);
    return {.success = false, .error = "Failed to get bitmap info"};
  }

  int width = bm.bmWidth;
  int height = bm.bmHeight;

  // Allocate buffer for RGBA data
  std::vector<uint8_t> data(width * height * 4);

  // Setup bitmap info header for GetDIBits
  BITMAPINFOHEADER bi = {};
  bi.biSize = sizeof(BITMAPINFOHEADER);
  bi.biWidth = width;
  bi.biHeight = -height; // Negative for top-down
  bi.biPlanes = 1;
  bi.biBitCount = 32;
  bi.biCompression = BI_RGB;

  HDC hdc = GetDC(nullptr);
  int result = GetDIBits(hdc, hBitmap, 0, height, data.data(),
                         reinterpret_cast<BITMAPINFO *>(&bi), DIB_RGB_COLORS);
  ReleaseDC(nullptr, hdc);
  DeleteObject(hBitmap);

  if (result == 0) {
    return {.success = false, .error = "Failed to get bitmap bits"};
  }

  // Convert BGRA to RGBA (Windows uses BGRA)
  for (size_t i = 0; i < data.size(); i += 4) {
    std::swap(data[i], data[i + 2]); // Swap B and R
  }

  return {.data = std::move(data),
          .width = width,
          .height = height,
          .success = true,
          .error = ""};
}

IconResult IconExtractor::extractJumboIcon(const std::wstring &path, int size) {
  // Use SHGetImageList to get jumbo (256x256) or extra-large (48x48) icons
  // Constants defined inline to avoid conflicts with Windows SDK
  constexpr int SHIL_JUMBO_SIZE = 4;      // 256x256
  constexpr int SHIL_EXTRALARGE_SIZE = 2; // 48x48

  // Get file info with icon index
  SHFILEINFOW shfi = {};
  DWORD_PTR result = SHGetFileInfoW(path.c_str(), 0, &shfi, sizeof(shfi),
                                    SHGFI_SYSICONINDEX | SHGFI_LARGEICON);

  if (!result) {
    return {.success = false, .error = "Failed to get file info"};
  }

  // Try to get IImageList for jumbo icons first, then fall back to extra-large
  IImageList *pImageList = nullptr;
  int imageListType = (size >= 256) ? SHIL_JUMBO_SIZE : SHIL_EXTRALARGE_SIZE;

  HRESULT hr = SHGetImageList(imageListType, IID_IImageList,
                              reinterpret_cast<void **>(&pImageList));
  if (FAILED(hr) || !pImageList) {
    // Try extra-large as fallback
    if (imageListType == SHIL_JUMBO_SIZE) {
      hr = SHGetImageList(SHIL_EXTRALARGE_SIZE, IID_IImageList,
                          reinterpret_cast<void **>(&pImageList));
    }
    if (FAILED(hr) || !pImageList) {
      return {.success = false, .error = "Failed to get image list"};
    }
  }

  // Get icon from image list
  HICON hIcon = nullptr;
  hr = pImageList->GetIcon(shfi.iIcon, ILD_TRANSPARENT, &hIcon);
  pImageList->Release();

  if (FAILED(hr) || !hIcon) {
    return {.success = false, .error = "Failed to get icon from image list"};
  }

  // Get icon info to determine size
  ICONINFO iconInfo = {};
  if (!GetIconInfo(hIcon, &iconInfo)) {
    DestroyIcon(hIcon);
    return {.success = false, .error = "Failed to get icon info"};
  }

  BITMAP bm = {};
  GetObject(iconInfo.hbmColor ? iconInfo.hbmColor : iconInfo.hbmMask,
            sizeof(bm), &bm);

  int width = bm.bmWidth;
  int height = abs(bm.bmHeight);

  // Create DC and bitmap for drawing
  HDC screenDC = GetDC(nullptr);
  HDC memDC = CreateCompatibleDC(screenDC);

  BITMAPINFO bmi = {};
  bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
  bmi.bmiHeader.biWidth = width;
  bmi.bmiHeader.biHeight = -height; // Top-down
  bmi.bmiHeader.biPlanes = 1;
  bmi.bmiHeader.biBitCount = 32;
  bmi.bmiHeader.biCompression = BI_RGB;

  void *pBits = nullptr;
  HBITMAP hBitmap =
      CreateDIBSection(memDC, &bmi, DIB_RGB_COLORS, &pBits, nullptr, 0);

  if (!hBitmap || !pBits) {
    DeleteDC(memDC);
    ReleaseDC(nullptr, screenDC);
    if (iconInfo.hbmColor)
      DeleteObject(iconInfo.hbmColor);
    if (iconInfo.hbmMask)
      DeleteObject(iconInfo.hbmMask);
    DestroyIcon(hIcon);
    return {.success = false, .error = "Failed to create DIB section"};
  }

  HBITMAP oldBitmap = (HBITMAP)SelectObject(memDC, hBitmap);

  // Clear background to transparent
  memset(pBits, 0, width * height * 4);

  // Draw icon with alpha channel
  DrawIconEx(memDC, 0, 0, hIcon, width, height, 0, nullptr, DI_NORMAL);

  // Copy pixel data
  std::vector<uint8_t> data(width * height * 4);
  memcpy(data.data(), pBits, data.size());

  // Cleanup
  SelectObject(memDC, oldBitmap);
  DeleteObject(hBitmap);
  DeleteDC(memDC);
  ReleaseDC(nullptr, screenDC);
  if (iconInfo.hbmColor)
    DeleteObject(iconInfo.hbmColor);
  if (iconInfo.hbmMask)
    DeleteObject(iconInfo.hbmMask);
  DestroyIcon(hIcon);

  // Convert BGRA to RGBA
  for (size_t i = 0; i < data.size(); i += 4) {
    std::swap(data[i], data[i + 2]);
  }

  return {.data = std::move(data),
          .width = width,
          .height = height,
          .success = true,
          .error = ""};
}

IconResult IconExtractor::extractFromExe(const std::wstring &path, int size) {
  HICON hIconLarge = nullptr;
  HICON hIconSmall = nullptr;

  UINT count = ExtractIconExW(path.c_str(), 0, &hIconLarge, &hIconSmall, 1);

  HICON hIcon = hIconLarge ? hIconLarge : hIconSmall;
  if (!hIcon || count == 0) {
    if (hIconLarge)
      DestroyIcon(hIconLarge);
    if (hIconSmall)
      DestroyIcon(hIconSmall);
    return {.success = false, .error = "No icon found in executable"};
  }

  // Get icon info
  ICONINFO iconInfo;
  if (!GetIconInfo(hIcon, &iconInfo)) {
    if (hIconLarge)
      DestroyIcon(hIconLarge);
    if (hIconSmall)
      DestroyIcon(hIconSmall);
    return {.success = false, .error = "Failed to get icon info"};
  }

  BITMAP bm;
  GetObject(iconInfo.hbmColor ? iconInfo.hbmColor : iconInfo.hbmMask,
            sizeof(bm), &bm);

  int width = bm.bmWidth;
  int height = bm.bmHeight;
  std::vector<uint8_t> data(width * height * 4);

  BITMAPINFOHEADER bi = {};
  bi.biSize = sizeof(BITMAPINFOHEADER);
  bi.biWidth = width;
  bi.biHeight = -height;
  bi.biPlanes = 1;
  bi.biBitCount = 32;
  bi.biCompression = BI_RGB;

  HDC hdc = GetDC(nullptr);
  GetDIBits(hdc, iconInfo.hbmColor ? iconInfo.hbmColor : iconInfo.hbmMask, 0,
            height, data.data(), reinterpret_cast<BITMAPINFO *>(&bi),
            DIB_RGB_COLORS);
  ReleaseDC(nullptr, hdc);

  // Cleanup
  if (iconInfo.hbmColor)
    DeleteObject(iconInfo.hbmColor);
  if (iconInfo.hbmMask)
    DeleteObject(iconInfo.hbmMask);
  if (hIconLarge)
    DestroyIcon(hIconLarge);
  if (hIconSmall)
    DestroyIcon(hIconSmall);

  // Convert BGRA to RGBA
  for (size_t i = 0; i < data.size(); i += 4) {
    std::swap(data[i], data[i + 2]);
  }

  return {.data = std::move(data),
          .width = width,
          .height = height,
          .success = true,
          .error = ""};
}

std::wstring IconExtractor::resolveShortcut(const std::wstring &lnkPath) {
  IShellLinkW *pShellLink = nullptr;
  IPersistFile *pPersistFile = nullptr;
  std::wstring result;

  HRESULT hr =
      CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER,
                       IID_IShellLinkW, reinterpret_cast<void **>(&pShellLink));

  if (FAILED(hr))
    return result;

  hr = pShellLink->QueryInterface(IID_IPersistFile,
                                  reinterpret_cast<void **>(&pPersistFile));
  if (FAILED(hr)) {
    pShellLink->Release();
    return result;
  }

  hr = pPersistFile->Load(lnkPath.c_str(), STGM_READ);
  if (SUCCEEDED(hr)) {
    wchar_t targetPath[MAX_PATH];
    hr = pShellLink->GetPath(targetPath, MAX_PATH, nullptr, SLGP_UNCPRIORITY);
    if (SUCCEEDED(hr)) {
      result = targetPath;
    }
  }

  pPersistFile->Release();
  pShellLink->Release();

  return result;
}

IconResult IconExtractor::extractFromLnk(const std::wstring &path, int size) {
  // First try to get icon from the shortcut itself
  auto result = extractWithShellApi(path, size);
  if (result.success)
    return result;

  // Resolve shortcut target and extract from there
  std::wstring target = resolveShortcut(path);
  if (!target.empty()) {
    result = extractWithShellApi(target, size);
    if (result.success)
      return result;

    // Try EXE extraction if target is an executable
    std::wstring ext = PathFindExtensionW(target.c_str());
    if (_wcsicmp(ext.c_str(), L".exe") == 0) {
      result = extractFromExe(target, size);
      if (result.success)
        return result;
    }
  }

  return {.success = false, .error = "Failed to extract icon from shortcut"};
}
#endif

std::vector<IconResult>
IconExtractor::extractBatch(const std::vector<std::string> &paths, int size,
                            int numThreads) {
  std::vector<IconResult> results(paths.size());
  std::atomic<size_t> nextIndex{0};

  auto worker = [&]() {
  // Each thread needs its own COM initialization
#ifdef _WIN32
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
#endif

    while (true) {
      size_t index = nextIndex.fetch_add(1);
      if (index >= paths.size())
        break;
      results[index] = extract(paths[index], size);
    }

#ifdef _WIN32
    CoUninitialize();
#endif
  };

  // Limit threads to reasonable number
  numThreads = std::min(numThreads, static_cast<int>(paths.size()));
  numThreads = std::max(numThreads, 1);

  std::vector<std::thread> threads;
  for (int i = 0; i < numThreads; ++i) {
    threads.emplace_back(worker);
  }

  for (auto &t : threads) {
    t.join();
  }

  return results;
}

IconResult IconExtractor::getVideoThumbnail(const std::string &path, int size) {
  // Use Shell API which can extract video thumbnails
  return extract(path, size);
}

} // namespace helxaid
