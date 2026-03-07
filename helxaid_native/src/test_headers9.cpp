#ifndef NOMINMAX
#define NOMINMAX
#endif

#ifdef _WIN32
#include <TlHelp32.h>
#include <Windows.h>
#include <shellapi.h>
#include <shlobj.h>
#include <winsvc.h>

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "shell32.lib")
#endif

#include <algorithm>
#include <chrono>
#include <fstream>
#include <functional>
#include <map>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

int main() { return 0; }
