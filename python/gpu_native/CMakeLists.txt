cmake_minimum_required(VERSION 3.15)
project(gpu_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Find Python first
find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

# Find pybind11 via Python (pip installed pybind11 provides cmake files)
execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c "import pybind11; print(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE pybind11_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE pybind11_result
)

if(pybind11_result EQUAL "0" AND EXISTS "${pybind11_DIR}")
    list(APPEND CMAKE_PREFIX_PATH "${pybind11_DIR}")
    find_package(pybind11 CONFIG REQUIRED)
else()
    # Fallback: try to find pybind11 in Python's site-packages
    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -c "import pybind11; print(pybind11.__path__[0])"
        OUTPUT_VARIABLE pybind11_path
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if(EXISTS "${pybind11_path}/share/cmake/pybind11")
        list(APPEND CMAKE_PREFIX_PATH "${pybind11_path}/share/cmake/pybind11")
        find_package(pybind11 CONFIG REQUIRED)
    else()
        message(FATAL_ERROR "Could not find pybind11 cmake files. Install with: pip install pybind11")
    endif()
endif()

# Create the Python extension module
pybind11_add_module(gpu_native
    bindings.cpp
)

# Link Windows libraries for DXGI and D3D11
target_link_libraries(gpu_native PRIVATE
    dxgi
    d3d11
    advapi32  # For registry functions
)

# Include directories
target_include_directories(gpu_native PRIVATE
    ${Python3_INCLUDE_DIRS}
)

# Compiler-specific options
if(MSVC)
    # MSVC compiler options
    target_compile_options(gpu_native PRIVATE
        /W4           # Warning level 4
        /utf-8        # Source and execution character set UTF-8
        /permissive-  # Strict conformance
    )
    
    # Define Windows version for DXGI 1.1
    target_compile_definitions(gpu_native PRIVATE
        _WIN32_WINNT=0x0601  # Windows 7 minimum
        WIN32_LEAN_AND_MEAN
        NOMINMAX
    )
else()
    # GCC/Clang options (for cross-compilation scenarios)
    target_compile_options(gpu_native PRIVATE
        -Wall
        -Wextra
        -Wpedantic
    )
endif()

# Output directory
set_target_properties(gpu_native PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)

# Install target (for pip install)
install(TARGETS gpu_native
    LIBRARY DESTINATION gpu_native
)

# Optional: Create a test target
if(BUILD_TESTING)
    add_executable(test_gpu_native test.cpp)
    target_link_libraries(test_gpu_native PRIVATE
        dxgi
        d3d11
        advapi32
    )
    target_compile_definitions(test_gpu_native PRIVATE
        _WIN32_WINNT=0x0601
        WIN32_LEAN_AND_MEAN
        NOMINMAX
    )
endif()
