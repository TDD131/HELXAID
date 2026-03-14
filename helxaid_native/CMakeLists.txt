cmake_minimum_required(VERSION 3.18)

# Force older, stable Windows SDK version (10.0.26100 has bugs)
set(CMAKE_SYSTEM_VERSION 10.0.22621.0)

project(helxaid_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Set build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Find Python
find_package(Python3 REQUIRED COMPONENTS Development Interpreter)
message(STATUS "Python3 found: ${Python3_EXECUTABLE}")
message(STATUS "Python3 include: ${Python3_INCLUDE_DIRS}")

# Add pybind11
add_subdirectory(third_party/pybind11)

# Source files
set(SOURCES
    src/bindings.cpp
    src/icon_extractor.cpp
    src/file_scanner.cpp
    src/game_detector.cpp
    src/media_player.cpp
    src/hardware_monitor.cpp
    src/input_hook.cpp
    src/macro_engine.cpp
    src/hid_controller.cpp
    src/boost_engine.cpp
    src/etw_network_monitor.cpp
)

# Header files
set(HEADERS
    include/helxaid.h
    include/icon_extractor.h
    include/file_scanner.h
    include/game_detector.h
    include/media_player.h
    include/hardware_monitor.h
    include/input_hook.h
    include/macro_engine.h
    include/hid_controller.h
    include/boost_engine.h
    include/etw_network_monitor.h
)

# Create Python module
pybind11_add_module(helxaid_native ${SOURCES} ${HEADERS})

# Include directories
target_include_directories(helxaid_native PRIVATE 
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Add Windows macros to prevent conflicts
if(WIN32)
    target_compile_definitions(helxaid_native PRIVATE
        NOMINMAX
    )
endif()
# Windows-specific configuration
if(WIN32)
    target_link_libraries(helxaid_native PRIVATE
        advapi32
        tdh
        shell32
        ole32
        gdi32
        user32
        shlwapi
        # Media Foundation for audio/video playback
        mf
        mfplat
        mfuuid
        mfreadwrite
        propsys
        # HID and SetupAPI for direct hardware communication
        setupapi
        hid
        # Process API for QueryFullProcessImageNameW
        psapi
    )
    
    # Disable annoying warnings
    target_compile_definitions(helxaid_native PRIVATE
        _CRT_SECURE_NO_WARNINGS
        NOMINMAX
    )
endif()

# Optimization flags for Release build
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    if(MSVC)
        target_compile_options(helxaid_native PRIVATE /O2 /GL)
        target_link_options(helxaid_native PRIVATE /LTCG)
    else()
        target_compile_options(helxaid_native PRIVATE -O3 -march=native)
    endif()
endif()

# Copy output to python directory for easy import
add_custom_command(TARGET helxaid_native POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy
        $<TARGET_FILE:helxaid_native>
        ${CMAKE_CURRENT_SOURCE_DIR}/../python/$<TARGET_FILE_NAME:helxaid_native>
    COMMENT "Copying helxaid_native to python directory"
)

# Print configuration summary
message(STATUS "")
message(STATUS "=== HELXAID Native Configuration ===")
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "Python version: ${Python3_VERSION}")
message(STATUS "Output directory: ${CMAKE_CURRENT_SOURCE_DIR}/../python/")
message(STATUS "====================================")
