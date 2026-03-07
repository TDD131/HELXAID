/**
 * Icon Extractor
 *
 * High-performance icon extraction using Windows Shell API.
 * Supports EXE, LNK, DLL, and other file types.
 */

#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

// No Windows.h needed in header - only standard library types

namespace helxaid {

/**
 * Result of icon extraction operation
 */
struct IconResult {
  std::vector<uint8_t> data; // Raw RGBA pixel data
  int width = 0;
  int height = 0;
  bool success = false;
  std::string error;

  // Check if result is valid
  bool isValid() const {
    return success && !data.empty() && width > 0 && height > 0;
  }

  // Get bytes for Python integration
  const uint8_t *getData() const { return data.data(); }
  size_t getDataSize() const { return data.size(); }
};

/**
 * High-performance icon extractor class
 */
class IconExtractor {
public:
  IconExtractor();
  ~IconExtractor();

  // Non-copyable
  IconExtractor(const IconExtractor &) = delete;
  IconExtractor &operator=(const IconExtractor &) = delete;

  // Movable
  IconExtractor(IconExtractor &&) noexcept;
  IconExtractor &operator=(IconExtractor &&) noexcept;

  /**
   * Extract icon from file
   * @param path Path to file (exe, lnk, dll, etc.)
   * @param size Desired icon size (default 256)
   * @return IconResult with RGBA data
   */
  IconResult extract(const std::string &path, int size = 256);

  /**
   * Extract icons from multiple files in parallel
   * @param paths List of file paths
   * @param size Desired icon size
   * @param numThreads Number of worker threads
   * @return List of IconResults
   */
  std::vector<IconResult> extractBatch(const std::vector<std::string> &paths,
                                       int size = 256, int numThreads = 4);

  /**
   * Extract video thumbnail
   * @param path Path to video file
   * @param size Desired thumbnail size
   * @return IconResult with thumbnail
   */
  IconResult getVideoThumbnail(const std::string &path, int size = 512);

private:
  struct Impl;
  std::unique_ptr<Impl> pImpl;

#ifdef _WIN32
  // Windows-specific extraction methods (use std::wstring from <string>)
  IconResult extractWithShellApi(const std::wstring &path, int size);
  IconResult extractJumboIcon(const std::wstring &path, int size);
  IconResult extractFromExe(const std::wstring &path, int size);
  IconResult extractFromLnk(const std::wstring &path, int size);
  std::wstring resolveShortcut(const std::wstring &lnkPath);
#endif
};

} // namespace helxaid
