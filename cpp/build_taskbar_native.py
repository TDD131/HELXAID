"""
Build Script for taskbar_native C++ Native Extension
"""
import os
import sys
import shutil
from setuptools import setup, Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
python_dir = os.path.join(root_dir, "python")
cpp_file = os.path.join(script_dir, "taskbar_native.cpp")

import pybind11

module = Extension(
    'taskbar_native',
    sources=[cpp_file],
    include_dirs=[pybind11.get_include()],
    libraries=['ole32', 'user32', 'shell32', 'gdi32', 'comctl32'],
    extra_compile_args=['/O2', '/EHsc', '/std:c++17', '/MD', '/DUNICODE', '/D_UNICODE']
)

# Run build_ext
sys.argv = [sys.argv[0], 'build_ext', '--inplace']

setup(
    name='taskbar_native',
    version='1.0',
    description='Native C++ Windows Taskbar & Media Control Integration for HELXAID',
    ext_modules=[module],
)

# Copy output .pyd to root and python/ folder
search_dirs = [root_dir, script_dir]
for sdir in search_dirs:
    if not os.path.exists(sdir):
        continue
    for fname in os.listdir(sdir):
        if fname.startswith("taskbar_native") and fname.endswith(".pyd"):
            src = os.path.join(sdir, fname)
            
            # Copy to python/ dir
            dst1 = os.path.join(python_dir, fname)
            try:
                shutil.copy2(src, dst1)
                print(f"[Build] Copied {fname} -> {python_dir}")
            except Exception as e:
                pass
            
            # Copy plain taskbar_native.pyd to python/
            plain_dst1 = os.path.join(python_dir, "taskbar_native.pyd")
            try:
                shutil.copy2(src, plain_dst1)
                print(f"[Build] Copied {fname} -> {plain_dst1}")
            except Exception as e:
                pass

            # Copy plain taskbar_native.pyd to root_dir
            plain_dst2 = os.path.join(root_dir, "taskbar_native.pyd")
            try:
                shutil.copy2(src, plain_dst2)
                print(f"[Build] Copied {fname} -> {plain_dst2}")
            except Exception as e:
                pass
