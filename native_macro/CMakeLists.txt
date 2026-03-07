cmake_minimum_required(VERSION 3.15)
project(helxairo_native VERSION 1.0.0 LANGUAGES CXX)

# C++ Standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Find Python
find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

# Find pybind11
find_package(pybind11 CONFIG QUIET)
if(NOT pybind11_FOUND)
    # Try to use pybind11 from pip
    execute_process(
        COMMAND ${Python3_EXECUTABLE} -c "import pybind11; print(pybind11.get_cmake_dir())"
        OUTPUT_VARIABLE PYBIND11_CMAKE_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE PYBIND11_RESULT
    )
    if(PYBIND11_RESULT EQUAL 0)
        list(APPEND CMAKE_PREFIX_PATH "${PYBIND11_CMAKE_DIR}")
        find_package(pybind11 CONFIG REQUIRED)
    else()
        message(FATAL_ERROR "pybind11 not found. Install with: pip install pybind11")
    endif()
endif()

# Source files
set(CORE_SOURCES
    src/input_hook.cpp
    src/input_simulator.cpp
    src/timer_manager.cpp
    src/macro_engine.cpp
    src/hid_controller.cpp
)

set(MACRO_SOURCES
    src/macros/base_macro.cpp
    src/macros/toggle_macro.cpp
)

set(BINDING_SOURCES
    bindings/python_bindings.cpp
)

# Include directories
include_directories(include)

# Create Python module
pybind11_add_module(helxairo_native 
    ${CORE_SOURCES}
    ${MACRO_SOURCES}
    ${BINDING_SOURCES}
)

# Link Windows libraries
target_link_libraries(helxairo_native PRIVATE
    user32
    kernel32
    setupapi
    hid
)

# Define NOMINMAX to prevent Windows.h min/max macros
target_compile_definitions(helxairo_native PRIVATE
    NOMINMAX
    WIN32_LEAN_AND_MEAN
)

# Compiler optimizations
if(MSVC)
    # Release optimizations
    target_compile_options(helxairo_native PRIVATE
        $<$<CONFIG:Release>:/O2>
        $<$<CONFIG:Release>:/GL>
        /W4
    )
    target_link_options(helxairo_native PRIVATE
        $<$<CONFIG:Release>:/LTCG>
    )
endif()

# Output directory - put in python folder for easy import
set_target_properties(helxairo_native PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../python"
    LIBRARY_OUTPUT_DIRECTORY_DEBUG "${CMAKE_SOURCE_DIR}/../python"
    LIBRARY_OUTPUT_DIRECTORY_RELEASE "${CMAKE_SOURCE_DIR}/../python"
)

# Print configuration
message(STATUS "Python: ${Python3_EXECUTABLE}")
message(STATUS "Python version: ${Python3_VERSION}")
message(STATUS "pybind11 version: ${pybind11_VERSION}")
message(STATUS "Output directory: ${CMAKE_SOURCE_DIR}/../python")
