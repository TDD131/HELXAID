/**
 * File Scanner Implementation
 */

#include "file_scanner.h"

#include <filesystem>
#include <algorithm>
#include <cctype>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

namespace {
// Helper to convert UTF-8 string to wide string on Windows
inline std::wstring utf8ToWide(const std::string& str) {
    if (str.empty()) return std::wstring();
    int size = MultiByteToWideChar(CP_UTF8, 0, str.c_str(), -1, nullptr, 0);
    if (size <= 1) return std::wstring();
    std::wstring result(size - 1, 0);
    MultiByteToWideChar(CP_UTF8, 0, str.c_str(), -1, &result[0], size);
    return result;
}

// Helper to convert wide string to UTF-8 on Windows
inline std::string wideToUtf8(const std::wstring& wstr) {
    if (wstr.empty()) return std::string();
    int size = WideCharToMultiByte(CP_UTF8, 0, wstr.c_str(), -1, nullptr, 0, nullptr, nullptr);
    if (size <= 1) return std::string();
    std::string result(size - 1, 0);
    WideCharToMultiByte(CP_UTF8, 0, wstr.c_str(), -1, &result[0], size, nullptr, nullptr);
    return result;
}
} // anonymous namespace
#endif

namespace fs = std::filesystem;

namespace helxaid {

// Helper to get lowercase extension
static std::string getLowerExt(const std::string& path) {
    size_t pos = path.rfind('.');
    if (pos == std::string::npos) return "";
    std::string ext = path.substr(pos);
    std::transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return ext;
}

std::vector<FileInfo> FileScanner::scan(
    const std::string& directory,
    bool recursive,
    FilterFunc filter
) {
    return scanDirectory(directory, recursive, filter);
}

std::vector<FileInfo> FileScanner::scanDirectory(
    const std::string& directory,
    bool recursive,
    FilterFunc filter
) {
    std::vector<FileInfo> results;
    
    try {
#ifdef _WIN32
        fs::path dirPath(utf8ToWide(directory));
#else
        fs::path dirPath = fs::u8path(directory);
#endif
        auto options = fs::directory_options::skip_permission_denied;
        
        if (recursive) {
            for (const auto& entry : fs::recursive_directory_iterator(dirPath, options)) {
                FileInfo info;
#ifdef _WIN32
                info.path = wideToUtf8(entry.path().wstring());
                info.name = wideToUtf8(entry.path().filename().wstring());
#else
                info.path = entry.path().u8string();
                info.name = entry.path().filename().u8string();
#endif
                info.extension = getLowerExt(info.name);
                info.isDirectory = entry.is_directory();
                
                if (!info.isDirectory) {
                    try {
                        info.size = entry.file_size();
                        info.modifiedTime = std::chrono::duration_cast<std::chrono::seconds>(
                            entry.last_write_time().time_since_epoch()
                        ).count();
                    } catch (...) {
                        info.size = 0;
                        info.modifiedTime = 0;
                    }
                }
                
                if (!filter || filter(info)) {
                    results.push_back(std::move(info));
                }
            }
        } else {
            for (const auto& entry : fs::directory_iterator(dirPath, options)) {
                FileInfo info;
#ifdef _WIN32
                info.path = wideToUtf8(entry.path().wstring());
                info.name = wideToUtf8(entry.path().filename().wstring());
#else
                info.path = entry.path().u8string();
                info.name = entry.path().filename().u8string();
#endif
                info.extension = getLowerExt(info.name);
                info.isDirectory = entry.is_directory();
                
                if (!info.isDirectory) {
                    try {
                        info.size = entry.file_size();
                        info.modifiedTime = std::chrono::duration_cast<std::chrono::seconds>(
                            entry.last_write_time().time_since_epoch()
                        ).count();
                    } catch (...) {
                        info.size = 0;
                        info.modifiedTime = 0;
                    }
                }
                
                if (!filter || filter(info)) {
                    results.push_back(std::move(info));
                }
            }
        }
    } catch (const std::exception& e) {
        // Directory doesn't exist or permission denied
    }
    
    return results;
}

std::vector<FileInfo> FileScanner::findExecutables(const std::string& directory) {
    static const std::vector<std::string> exeExtensions = {
        ".exe", ".lnk", ".url", ".bat", ".cmd"
    };
    
    return scan(directory, true, [](const FileInfo& info) {
        if (info.isDirectory) return false;
        for (const auto& ext : exeExtensions) {
            if (info.extension == ext) return true;
        }
        return false;
    });
}

std::vector<FileInfo> FileScanner::findMediaFiles(const std::string& directory) {
    static const std::vector<std::string> mediaExtensions = {
        // Audio
        ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma",
        // Video
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"
    };
    
    return scan(directory, true, [](const FileInfo& info) {
        if (info.isDirectory) return false;
        for (const auto& ext : mediaExtensions) {
            if (info.extension == ext) return true;
        }
        return false;
    });
}

} // namespace helxaid
