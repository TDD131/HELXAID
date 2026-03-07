/**
 * File Scanner Implementation
 */

#include "file_scanner.h"

#include <filesystem>
#include <algorithm>
#include <cctype>

namespace fs = std::filesystem;

namespace helxaid {

// Helper to get lowercase extension
static std::string getLowerExt(const std::string& path) {
    size_t pos = path.rfind('.');
    if (pos == std::string::npos) return "";
    std::string ext = path.substr(pos);
    std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
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
        auto options = recursive ? 
            fs::directory_options::skip_permission_denied :
            fs::directory_options::skip_permission_denied;
        
        if (recursive) {
            for (const auto& entry : fs::recursive_directory_iterator(directory, options)) {
                FileInfo info;
                info.path = entry.path().string();
                info.name = entry.path().filename().string();
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
            for (const auto& entry : fs::directory_iterator(directory, options)) {
                FileInfo info;
                info.path = entry.path().string();
                info.name = entry.path().filename().string();
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
