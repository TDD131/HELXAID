"""
Build Script for image_cache_native C++ Native Extension
"""
import os
import sys
import shutil
from setuptools import setup, Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
python_dir = os.path.join(root_dir, "python")
cpp_file = os.path.join(script_dir, "image_cache_native.cpp")

module = Extension(
    'image_cache_native',
    sources=[cpp_file],
    libraries=['ole32', 'oleaut32', 'windowscodecs', 'winhttp', 'advapi32'],
    extra_compile_args=['/O2', '/EHsc', '/std:c++17', '/MD']
)

# Run build_ext
sys.argv = [sys.argv[0], 'build_ext', '--inplace']

setup(
    name='image_cache_native',
    version='1.0',
    description='High-Performance Native C++ WIC Image Resizer & LRU Cache for HELXAID',
    ext_modules=[module],
)

# Copy output .pyd to python/ folder as well
search_dirs = [root_dir, script_dir]
for sdir in search_dirs:
    for fname in os.listdir(sdir):
        if fname.startswith("image_cache_native") and fname.endswith(".pyd"):
            src = os.path.join(sdir, fname)
            dst = os.path.join(python_dir, fname)
            try:
                shutil.copy2(src, dst)
                print(f"[Build] Copied {fname} -> {python_dir}")
            except Exception as e:
                print(f"[Build] Could not copy {fname} to {python_dir}: {e}")
            
            # Also copy plain image_cache_native.pyd for universal import
            plain_dst = os.path.join(python_dir, "image_cache_native.pyd")
            try:
                shutil.copy2(src, plain_dst)
                print(f"[Build] Copied {fname} -> {plain_dst}")
            except Exception as e:
                pass
