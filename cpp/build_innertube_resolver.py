"""
Build Script for innertube_fast_resolver C++ Native Extension
"""
import os
import sys
import shutil
from setuptools import setup, Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
python_dir = os.path.join(root_dir, "python")
cpp_file = os.path.join(script_dir, "innertube_fast_resolver.cpp")

module = Extension(
    'innertube_fast_resolver',
    sources=[cpp_file],
    libraries=['winhttp'],
    extra_compile_args=['/O2', '/EHsc', '/std:c++17', '/MD']
)

# Run build_ext
sys.argv = [sys.argv[0], 'build_ext', '--inplace']

setup(
    name='innertube_fast_resolver',
    version='1.0',
    description='Ultra-fast Innertube Stream Resolver for HELXAID',
    ext_modules=[module],
)

# Copy output .pyd to python/ folder as well
for fname in os.listdir(script_dir):
    if fname.startswith("innertube_fast_resolver") and fname.endswith(".pyd"):
        src = os.path.join(script_dir, fname)
        dst = os.path.join(python_dir, fname)
        try:
            shutil.copy2(src, dst)
            print(f"[Build] Copied {fname} -> {python_dir}")
        except Exception as e:
            print(f"[Build] Could not copy {fname} to {python_dir} (may be locked by running instance): {e}")
        
        # Also copy plain innertube_fast_resolver.pyd for universal import
        plain_dst = os.path.join(python_dir, "innertube_fast_resolver.pyd")
        try:
            shutil.copy2(src, plain_dst)
            print(f"[Build] Copied {fname} -> {plain_dst}")
        except Exception as e:
            pass

