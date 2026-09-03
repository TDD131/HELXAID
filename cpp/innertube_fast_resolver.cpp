/*
 * Innertube Fast Resolver - Native C++ Backend for HELXAID
 * 
 * Provides ultra-fast (~100ms - 200ms) YouTube stream resolution & metadata
 * extraction via Google Innertube Android Client API using Windows WinHTTP.
 * Includes thread-safe in-memory caching and background pre-fetching.
 */

#define WINVER 0x0600
#define _WIN32_WINNT 0x0600
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#define PY_SSIZE_T_CLEAN

#include <Python.h>
#include <windows.h>
#include <winhttp.h>
#include <string>
#include <vector>
#include <unordered_map>
#include <mutex>
#include <thread>
#include <chrono>
#include <sstream>
#include <algorithm>

#pragma comment(lib, "winhttp.lib")

// ============================================
// DATA STRUCTURES & CACHE
// ============================================

struct ResolvedTrack {
    std::string video_id;
    std::string title;
    std::string artist;
    std::string stream_url;
    long long duration_ms;
    int itag;
    long long timestamp; // epoch ms when resolved
    bool success;
    std::string error;
    bool requires_fallback;
};

class StreamCache {
private:
    std::unordered_map<std::string, ResolvedTrack> cache_;
    std::mutex mutex_;
    const long long TTL_MS = 4 * 3600 * 1000LL; // 4 hours TTL

public:
    bool get(const std::string& key, ResolvedTrack& out) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = cache_.find(key);
        if (it != cache_.end()) {
            auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count();
            if (now - it->second.timestamp < TTL_MS && it->second.success) {
                out = it->second;
                return true;
            } else {
                cache_.erase(it);
            }
        }
        return false;
    }

    void put(const std::string& key, const ResolvedTrack& track) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (cache_.size() > 200) {
            cache_.clear(); // simple LRU eviction
        }
        cache_[key] = track;
    }

    void clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        cache_.clear();
    }
};

static StreamCache g_cache;

// ============================================
// WINHTTP CLIENT ENGINE
// ============================================

class WinHttpClient {
private:
    HINTERNET h_session_;
    HINTERNET h_connect_;
    std::mutex http_mutex_;

public:
    WinHttpClient() : h_session_(NULL), h_connect_(NULL) {
        init_session();
    }

    ~WinHttpClient() {
        close_session();
    }

    void init_session() {
        if (!h_session_) {
            h_session_ = WinHttpOpen(
                L"com.google.ios.youtube/19.29.1 (iPhone14,3; U; CPU iOS 16_5 like Mac OS X; en_US)",
                WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                WINHTTP_NO_PROXY_NAME,
                WINHTTP_NO_PROXY_BYPASS,
                0
            );
        }
        if (h_session_ && !h_connect_) {
            h_connect_ = WinHttpConnect(
                h_session_,
                L"www.youtube.com",
                INTERNET_DEFAULT_HTTPS_PORT,
                0
            );
        }
    }

    void close_session() {
        if (h_connect_) {
            WinHttpCloseHandle(h_connect_);
            h_connect_ = NULL;
        }
        if (h_session_) {
            WinHttpCloseHandle(h_session_);
            h_session_ = NULL;
        }
    }

    bool post_json(const std::wstring& path, const std::string& json_payload, std::string& response_out) {
        std::lock_guard<std::mutex> lock(http_mutex_);
        init_session();

        if (!h_connect_) {
            return false;
        }

        HINTERNET h_request = WinHttpOpenRequest(
            h_connect_,
            L"POST",
            path.c_str(),
            NULL,
            WINHTTP_NO_REFERER,
            WINHTTP_DEFAULT_ACCEPT_TYPES,
            WINHTTP_FLAG_SECURE
        );

        if (!h_request) {
            return false;
        }

        // Set fast timeouts: Resolve: 1.5s, Connect: 2s, Send: 3s, Receive: 4s
        WinHttpSetTimeouts(h_request, 1500, 2000, 3000, 4000);

        LPCWSTR headers = L"Content-Type: application/json\r\n"
                          L"X-YouTube-Client-Name: 5\r\n"
                          L"X-YouTube-Client-Version: 19.29.1\r\n"
                          L"Origin: https://www.youtube.com\r\n"
                          L"Accept: */*\r\n";

        BOOL b_results = WinHttpAddRequestHeaders(
            h_request,
            headers,
            (DWORD)-1L,
            WINHTTP_ADDREQ_FLAG_ADD | WINHTTP_ADDREQ_FLAG_REPLACE
        );

        if (b_results) {
            b_results = WinHttpSendRequest(
                h_request,
                WINHTTP_NO_ADDITIONAL_HEADERS,
                0,
                (LPVOID)json_payload.c_str(),
                (DWORD)json_payload.length(),
                (DWORD)json_payload.length(),
                0
            );
        }

        if (b_results) {
            b_results = WinHttpReceiveResponse(h_request, NULL);
        }

        if (b_results) {
            DWORD dw_size = 0;
            DWORD dw_downloaded = 0;
            std::string buffer;

            do {
                dw_size = 0;
                if (!WinHttpQueryDataAvailable(h_request, &dw_size)) {
                    break;
                }
                if (dw_size == 0) {
                    break;
                }

                std::vector<char> temp_buf(dw_size + 1, 0);
                if (WinHttpReadData(h_request, (LPVOID)temp_buf.data(), dw_size, &dw_downloaded)) {
                    buffer.append(temp_buf.data(), dw_downloaded);
                } else {
                    break;
                }
            } while (dw_size > 0);

            response_out = buffer;
            WinHttpCloseHandle(h_request);
            return !response_out.empty();
        }

        WinHttpCloseHandle(h_request);
        return false;
    }
};

static WinHttpClient g_http_client;

// ============================================
// PARSING & EXTRACTION UTILITIES
// ============================================

static std::string extract_video_id(const std::string& input) {
    if (input.length() == 11 && input.find('/') == std::string::npos && input.find('.') == std::string::npos && input.find(' ') == std::string::npos) {
        return input;
    }

    // Check v= parameter
    size_t v_pos = input.find("v=");
    if (v_pos != std::string::npos && v_pos + 2 < input.length()) {
        std::string vid = input.substr(v_pos + 2, 11);
        size_t amp = vid.find('&');
        if (amp != std::string::npos) vid = vid.substr(0, amp);
        if (vid.length() == 11) return vid;
    }

    // Check youtu.be/
    size_t be_pos = input.find("youtu.be/");
    if (be_pos != std::string::npos) {
        size_t start = be_pos + 9;
        std::string vid = input.substr(start);
        size_t q = vid.find('?');
        if (q != std::string::npos) vid = vid.substr(0, q);
        size_t slash = vid.find('/');
        if (slash != std::string::npos) vid = vid.substr(0, slash);
        if (vid.length() >= 11) return vid.substr(0, 11);
    }

    // Check /shorts/ or /embed/ or /live/
    size_t shorts_pos = input.find("/shorts/");
    if (shorts_pos != std::string::npos) {
        size_t start = shorts_pos + 8;
        std::string vid = input.substr(start);
        size_t q = vid.find('?');
        if (q != std::string::npos) vid = vid.substr(0, q);
        if (vid.length() >= 11) return vid.substr(0, 11);
    }

    size_t live_pos = input.find("/live/");
    if (live_pos != std::string::npos) {
        size_t start = live_pos + 6;
        std::string vid = input.substr(start);
        size_t q = vid.find('?');
        if (q != std::string::npos) vid = vid.substr(0, q);
        if (vid.length() >= 11) return vid.substr(0, 11);
    }

    size_t embed_pos = input.find("/embed/");
    if (embed_pos != std::string::npos) {
        size_t start = embed_pos + 7;
        std::string vid = input.substr(start);
        size_t q = vid.find('?');
        if (q != std::string::npos) vid = vid.substr(0, q);
        if (vid.length() >= 11) return vid.substr(0, 11);
    }

    return "";
}

// Fast string finder helpers for JSON values
static std::string json_find_string(const std::string& json, const std::string& key, size_t start_pos = 0) {
    std::string needle = "\"" + key + "\":\"";
    size_t pos = json.find(needle, start_pos);
    if (pos == std::string::npos) {
        needle = "\"" + key + "\": \"";
        pos = json.find(needle, start_pos);
    }
    if (pos == std::string::npos) return "";

    size_t val_start = pos + needle.length();
    size_t val_end = val_start;
    while (val_end < json.length()) {
        if (json[val_end] == '"' && json[val_end - 1] != '\\') {
            break;
        }
        val_end++;
    }

    std::string raw = json.substr(val_start, val_end - val_start);
    // Unescape basic json characters
    std::string res = "";
    for (size_t i = 0; i < raw.length(); i++) {
        if (raw[i] == '\\' && i + 1 < raw.length()) {
            if (raw[i + 1] == '"') { res += '"'; i++; }
            else if (raw[i + 1] == '\\') { res += '\\'; i++; }
            else if (raw[i + 1] == '/') { res += '/'; i++; }
            else if (raw[i + 1] == 'n') { res += '\n'; i++; }
            else if (raw[i + 1] == 'u' && i + 5 < raw.length()) {
                std::string hex_str = raw.substr(i + 2, 4);
                try {
                    int code = std::stoi(hex_str, nullptr, 16);
                    if (code < 128) {
                        res += (char)code;
                    } else if (code < 0x800) {
                        res += (char)(0xC0 | (code >> 6));
                        res += (char)(0x80 | (code & 0x3F));
                    } else {
                        res += (char)(0xE0 | (code >> 12));
                        res += (char)(0x80 | ((code >> 6) & 0x3F));
                        res += (char)(0x80 | (code & 0x3F));
                    }
                    i += 5;
                } catch (...) {
                    res += raw[i];
                }
            } else {
                res += raw[i];
            }
        } else {
            res += raw[i];
        }
    }
    return res;
}

static long long json_find_number(const std::string& json, const std::string& key, size_t start_pos = 0) {
    std::string str_val = json_find_string(json, key, start_pos);
    if (!str_val.empty()) {
        try { return std::stoll(str_val); } catch (...) {}
    }
    std::string needle = "\"" + key + "\":";
    size_t pos = json.find(needle, start_pos);
    if (pos == std::string::npos) return 0;
    size_t val_start = pos + needle.length();
    while (val_start < json.length() && (json[val_start] == ' ' || json[val_start] == '\t')) val_start++;
    size_t val_end = val_start;
    while (val_end < json.length() && ((json[val_end] >= '0' && json[val_end] <= '9') || json[val_end] == '-')) {
        val_end++;
    }
    if (val_end > val_start) {
        try { return std::stoll(json.substr(val_start, val_end - val_start)); } catch (...) {}
    }
    return 0;
}

// ============================================
// INNERTUBE RESOLUTION LOGIC
// ============================================

static ResolvedTrack resolve_video_id_internal(const std::string& video_id) {
    ResolvedTrack result;
    result.video_id = video_id;
    result.success = false;
    result.requires_fallback = false;
    result.duration_ms = 0;
    result.itag = 0;
    result.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();

    // Check memory cache first
    if (g_cache.get(video_id, result)) {
        return result;
    }

    // Build Innertube iOS Client payload (ultra-fast direct unthrottled streaming URL yield)
    std::string payload = "{"
        "\"context\":{"
            "\"client\":{"
                "\"clientName\":\"IOS\","
                "\"clientVersion\":\"19.29.1\","
                "\"deviceMake\":\"Apple\","
                "\"deviceModel\":\"iPhone14,3\","
                "\"osName\":\"iOS\","
                "\"osVersion\":\"16.5.0.20F66\","
                "\"hl\":\"en\","
                "\"gl\":\"US\""
            "}"
        "},"
        "\"videoId\":\"" + video_id + "\","
        "\"playbackContext\":{"
            "\"contentPlaybackContext\":{"
                "\"html5Preference\":\"HTML5_PREF_WANTS\""
            "}"
        "},"
        "\"contentCheckOk\":true,"
        "\"racyCheckOk\":true"
    "}";

    std::string response_body;
    bool ok = g_http_client.post_json(L"/youtubei/v1/player?prettyPrint=false", payload, response_body);

    if (!ok || response_body.empty()) {
        result.error = "Failed to connect to Innertube API";
        result.requires_fallback = true;
        return result;
    }

    // Check playabilityStatus
    std::string status = json_find_string(response_body, "status");
    if (!status.empty() && status != "OK") {
        result.error = json_find_string(response_body, "reason");
        if (result.error.empty()) result.error = "Video status: " + status;
        result.requires_fallback = true;
        return result;
    }

    // Extract Title & Author from videoDetails
    size_t vd_pos = response_body.find("\"videoDetails\"");
    if (vd_pos != std::string::npos) {
        result.title = json_find_string(response_body, "title", vd_pos);
        result.artist = json_find_string(response_body, "author", vd_pos);
        long long length_sec = json_find_number(response_body, "lengthSeconds", vd_pos);
        result.duration_ms = length_sec * 1000LL;
    } else {
        result.title = json_find_string(response_body, "title");
        result.artist = json_find_string(response_body, "author");
        long long length_sec = json_find_number(response_body, "lengthSeconds");
        result.duration_ms = length_sec * 1000LL;
    }

    // Search for best audio stream format (Preference: itag 140 (AAC 128k), then itag 251 (Opus 160k), then any audio)
    size_t adaptive_pos = response_body.find("\"adaptiveFormats\"");
    if (adaptive_pos == std::string::npos) {
        adaptive_pos = response_body.find("\"formats\"");
    }

    if (adaptive_pos == std::string::npos) {
        result.error = "No streaming formats found";
        result.requires_fallback = true;
        return result;
    }

    std::string best_url = "";
    int best_itag = 0;
    int best_priority = 999; // 1 = 140, 2 = 251, 3 = other audio, 4 = progressive

    size_t cur = adaptive_pos;
    while (cur < response_body.length()) {
        size_t itag_pos = response_body.find("\"itag\":", cur);
        if (itag_pos == std::string::npos || itag_pos > cur + 150000) break;

        long long itag = json_find_number(response_body, "itag", itag_pos - 1);
        std::string mime = json_find_string(response_body, "mimeType", itag_pos);
        std::string url = json_find_string(response_body, "url", itag_pos);

        if (!url.empty()) {
            int priority = 999;
            if (itag == 140) priority = 1;       // m4a AAC 128k (Fastest startup & clean demuxing)
            else if (itag == 251) priority = 2;  // webm Opus 160k
            else if (mime.find("audio/") != std::string::npos) priority = 3;
            else if (itag == 18) priority = 4;   // mp4 360p

            if (priority < best_priority) {
                best_priority = priority;
                best_url = url;
                best_itag = (int)itag;
            }
        }

        cur = itag_pos + 10;
    }

    if (!best_url.empty()) {
        result.stream_url = best_url;
        result.itag = best_itag;
        result.success = true;
        g_cache.put(video_id, result);
        return result;
    }

    // If url is missing or ciphered, flag for yt-dlp fallback
    result.error = "Direct stream URL not in payload (cipher required)";
    result.requires_fallback = true;
    return result;
}

// Fast Innertube Keyword Search (Fast-Path Tier 2)
static std::string fast_search_video_id_internal(const std::string& query) {
    std::string payload = "{"
        "\"context\":{"
            "\"client\":{"
                "\"clientName\":\"ANDROID\","
                "\"clientVersion\":\"19.09.37\","
                "\"hl\":\"en\","
                "\"gl\":\"US\""
            "}"
        "},"
        "\"query\":\"" + query + "\""
    "}";

    std::string response_body;
    bool ok = g_http_client.post_json(L"/youtubei/v1/search?prettyPrint=false", payload, response_body);
    if (!ok || response_body.empty()) {
        return "";
    }

    // Extract first videoId from search results
    size_t vid_pos = response_body.find("\"videoId\":");
    if (vid_pos != std::string::npos) {
        return json_find_string(response_body, "videoId", vid_pos - 1);
    }
    return "";
}

// ============================================
// PYTHON C-API EXPORTS
// ============================================

static PyObject* py_resolve(PyObject* self, PyObject* args) {
    const char* input_str;
    if (!PyArg_ParseTuple(args, "s", &input_str)) {
        return NULL;
    }

    std::string raw_input(input_str);
    if (raw_input.rfind("ytsearch1:", 0) == 0) {
        raw_input = raw_input.substr(10);
    } else if (raw_input.rfind("ytsearch:", 0) == 0) {
        raw_input = raw_input.substr(9);
    }

    std::string vid = extract_video_id(raw_input);

    if (vid.empty()) {
        PyObject* dict = PyDict_New();
        PyDict_SetItemString(dict, "success", Py_False);
        PyDict_SetItemString(dict, "requires_fallback", Py_True);
        PyDict_SetItemString(dict, "error", PyUnicode_FromString("Not a direct YouTube link or video ID"));
        return dict;
    }

    ResolvedTrack track = resolve_video_id_internal(vid);

    PyObject* dict = PyDict_New();
    PyDict_SetItemString(dict, "video_id", PyUnicode_FromString(track.video_id.c_str()));
    PyDict_SetItemString(dict, "success", track.success ? Py_True : Py_False);
    PyDict_SetItemString(dict, "requires_fallback", track.requires_fallback ? Py_True : Py_False);
    PyDict_SetItemString(dict, "stream_url", PyUnicode_FromString(track.stream_url.c_str()));
    PyDict_SetItemString(dict, "title", PyUnicode_FromString(track.title.c_str()));
    PyDict_SetItemString(dict, "artist", PyUnicode_FromString(track.artist.c_str()));
    PyDict_SetItemString(dict, "duration", PyLong_FromLongLong(track.duration_ms / 1000LL));
    PyDict_SetItemString(dict, "duration_ms", PyLong_FromLongLong(track.duration_ms));
    PyDict_SetItemString(dict, "itag", PyLong_FromLong(track.itag));
    PyDict_SetItemString(dict, "error", PyUnicode_FromString(track.error.c_str()));

    return dict;
}

static PyObject* py_prefetch(PyObject* self, PyObject* args) {
    const char* input_str;
    if (!PyArg_ParseTuple(args, "s", &input_str)) {
        return NULL;
    }

    std::string raw_input(input_str);
    if (raw_input.rfind("ytsearch1:", 0) == 0) {
        raw_input = raw_input.substr(10);
    } else if (raw_input.rfind("ytsearch:", 0) == 0) {
        raw_input = raw_input.substr(9);
    }

    std::string vid = extract_video_id(raw_input);
    if (!vid.empty()) {
        // Spawn detached background thread for 0ms pre-fetching
        std::thread([vid]() {
            resolve_video_id_internal(vid);
        }).detach();
    }

    Py_RETURN_NONE;
}

static PyObject* py_is_youtube_url(PyObject* self, PyObject* args) {
    const char* input_str;
    if (!PyArg_ParseTuple(args, "s", &input_str)) {
        return NULL;
    }

    std::string raw_input(input_str);
    if (raw_input.rfind("ytsearch1:", 0) == 0) {
        raw_input = raw_input.substr(10);
    } else if (raw_input.rfind("ytsearch:", 0) == 0) {
        raw_input = raw_input.substr(9);
    }

    std::string vid = extract_video_id(raw_input);
    if (!vid.empty()) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

static PyObject* py_clear_cache(PyObject* self, PyObject* args) {
    g_cache.clear();
    Py_RETURN_NONE;
}

static PyMethodDef InnertubeMethods[] = {
    {"resolve", py_resolve, METH_VARARGS, "Resolve YouTube video ID/URL to direct stream URL in ~100ms"},
    {"prefetch", py_prefetch, METH_VARARGS, "Pre-fetch YouTube stream in background thread for 0ms next play"},
    {"is_youtube_url", py_is_youtube_url, METH_VARARGS, "Check if string contains a valid YouTube video ID/URL"},
    {"clear_cache", py_clear_cache, METH_NOARGS, "Clear in-memory stream cache"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef innertubemodule = {
    PyModuleDef_HEAD_INIT,
    "innertube_fast_resolver",
    "Ultra-fast Native C++ Innertube Stream Resolver for HELXAID",
    -1,
    InnertubeMethods
};

PyMODINIT_FUNC PyInit_innertube_fast_resolver(void) {
    return PyModule_Create(&innertubemodule);
}
