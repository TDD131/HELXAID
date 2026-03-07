/**
 * File Scanner
 * 
 * High-performance directory scanning for game discovery.
 */

#pragma once

#include <string>
#include <vector>
#include <functional>
#include <cstdint>

namespace helxaid {

/**
 * File information structure
 */
struct FileInfo {
    std::string path;
    std::string name;
    std::string extension;
    uint64_t size = 0;
    int64_t modifiedTime = 0;
    bool isDirectory = false;
};

/**
 * High-performance file scanner
 */
class FileScanner {
public:
    using FilterFunc = std::function<bool(const FileInfo&)>;
    using ProgressFunc = std::function<void(int current, int total)>;
    
    FileScanner() = default;
    ~FileScanner() = default;
    
    /**
     * Scan directory for files
     * @param directory Path to scan
     * @param recursive Include subdirectories
     * @param filter Optional filter function
     * @return List of matching files
     */
    std::vector<FileInfo> scan(
        const std::string& directory,
        bool recursive = true,
        FilterFunc filter = nullptr
    );
    
    /**
     * Find executable files (.exe, .lnk, .url)
     * @param directory Path to scan
     * @return List of executables
     */
    std::vector<FileInfo> findExecutables(const std::string& directory);
    
    /**
     * Find media files (audio/video)
     * @param directory Path to scan
     * @return List of media files
     */
    std::vector<FileInfo> findMediaFiles(const std::string& directory);

private:
    std::vector<FileInfo> scanDirectory(
        const std::string& directory,
        bool recursive,
        FilterFunc filter
    );
};

} // namespace helxaid
