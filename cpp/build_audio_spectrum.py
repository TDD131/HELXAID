"""
Build Script for audio_spectrum_native C++ Native Extension
"""
import os
import sys
import shutil
from setuptools import setup, Extension

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
python_dir = os.path.join(root_dir, "python")
cpp_file = os.path.join(script_dir, "audio_spectrum_native.cpp")

module = Extension(
    'audio_spectrum_native',
    sources=[cpp_file],
    libraries=['ole32', 'advapi32'],
    extra_compile_args=['/O2', '/EHsc', '/std:c++17', '/MD']
)

# Run build_ext
sys.argv = [sys.argv[0], 'build_ext', '--inplace']

setup(
    name='audio_spectrum_native',
    version='1.0',
    description='Ultra-fast Native Audio Spectrum Engine for HELXAIC',
    ext_modules=[module],
)

# Copy output .pyd to python/ folder and ensure copies exist everywhere
search_dirs = [root_dir, script_dir]
for sdir in search_dirs:
    for fname in os.listdir(sdir):
        if fname.startswith("audio_spectrum_native") and fname.endswith(".pyd"):
            src = os.path.join(sdir, fname)
            dst = os.path.join(python_dir, fname)
            try:
                shutil.copy2(src, dst)
                print(f"[Build] Copied {fname} -> {python_dir}")
            except Exception as e:
                pass
            
            # Also copy plain audio_spectrum_native.pyd for universal import
            plain_dst = os.path.join(python_dir, "audio_spectrum_native.pyd")
            try:
                shutil.copy2(src, plain_dst)
                print(f"[Build] Copied {fname} -> {plain_dst}")
            except Exception as e:
                pass

