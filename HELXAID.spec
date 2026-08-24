# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

build_name = os.environ.get('HELXAID_BUILD_NAME', 'HELXAID')

datas = [
    ('python/UI Icons', 'UI Icons'),
    ('python/UI Sidebar Icons', 'UI Sidebar Icons'),
    ('python/UI Reguler', 'UI Reguler'),
    ('python/UI Taskbar Icons', 'UI Taskbar Icons'),
    ('python/icons', 'icons'),
    ('python/Fonts', 'Fonts'),
    ('python/helxaid_native.cp314-win_amd64.pyd', '.'),
    ('python/helxairo_native.cp314-win_amd64.pyd', '.'),
    ('python/hardware_utils.cp314-win_amd64.pyd', '.'),
    ('python/hardware_utils.pyd', '.'),
]
binaries = [
    ('python/helxaid_native.cp314-win_amd64.pyd', '.'),
    ('python/helxairo_native.cp314-win_amd64.pyd', '.'),
    ('python/hardware_utils.cp314-win_amd64.pyd', '.'),
    ('python/hardware_utils.pyd', '.'),
]
hiddenimports = [
    'hardware_utils',
    'hardware_wrapper',
    'native_wrapper',
    'helxaid_native',
    'helxairo_native',
    'hid',
    'yt_dlp',
    'win32timezone',
    'win32serviceutil',
    'servicemanager',
    'win32com',
    'win32com.client',
    'pythoncom',
    'clr',
    'clr_loader',
    'pythonnet',
    'core.lhm_wrapper',
    'WindowsSMTCService',
    'winrt',
    'winrt.windows.media',
    'winrt.windows.media.playback',
    'winrt.windows.foundation',
    'winrt.windows.storage.streams',
]

# Collect all resources and binaries for critical packages
for pkg in ['PIL', 'mutagen', 'hid', 'hidapi', 'winrt']:
    tmp_datas, tmp_binaries, tmp_hidden = collect_all(pkg)
    datas.extend(tmp_datas)
    binaries.extend(tmp_binaries)
    hiddenimports.extend(tmp_hidden)

a = Analysis(
    ['python/launcher.py'],
    pathex=['python', '.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'scipy', 'pandas', 'matplotlib', 'tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure)

# 1. Onedir Mode Build
exe_dir = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=build_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['python/UI Icons/launcher-icon.ico'],
)

coll = COLLECT(
    exe_dir,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=build_name,
)

# 2. Standalone Onefile Mode Build (reuses Analysis & PYZ in single pass)
exe_file = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f"{build_name}.exe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['python/UI Icons/launcher-icon.ico'],
)
