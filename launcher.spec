# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

# Get the python directory
python_dir = os.path.dirname(os.path.abspath(SPEC))

# Data files to include
datas = [
    # UI Icons
    (os.path.join(python_dir, 'UI Icons'), 'UI Icons'),
    (os.path.join(python_dir, 'UI Taskbar Icons'), 'UI Taskbar Icons'),
    # assets folder NOT bundled - contains WinRing0 driver that triggers virus detection
    # RyzenAdj should be downloaded separately by user if they want CPU control
    # (os.path.join(python_dir, 'assets'), 'assets'),
    (os.path.join(python_dir, 'icons'), 'icons'),
    (os.path.join(python_dir, 'fonts'), 'fonts'),  # Orbitron font bundle
    # Config/Database files - NOTE: config.json, settings.json are NOT included,
    # they will be created empty on first launch to ensure fresh installs have empty library/settings
    # (os.path.join(python_dir, 'settings.json'), '.'),  # NOT bundled - created on first run
    (os.path.join(python_dir, 'audio_settings.json'), '.'),
    (os.path.join(python_dir, 'crosshair_settings.json'), '.'),
    # Macro system - macro_profiles NOT bundled to ensure empty on first launch
    # (os.path.join(python_dir, 'macro_profiles'), 'macro_profiles'),  # NOT bundled
    (os.path.join(python_dir, 'macro_scripts'), 'macro_scripts'),
    (os.path.join(python_dir, 'macro_system'), 'macro_system'),
]

# Hidden imports for dynamic imports
hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui', 
    'PySide6.QtWidgets',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'keyboard',
    'psutil',
    'PIL',
    'PIL.Image',
    'pydub',
    'win32api',
    'win32gui',
    'win32con',
    'win32com',
    'win32com.client',
    'ctypes',
    'ctypes.wintypes',
    'macro_system',
    'macro_system.core',
    'macro_system.core.input_listener',
    'macro_system.core.input_simulator',
    'macro_system.core.timer_manager',
    'macro_system.core.macro_engine',
    'macro_system.core.macro_recorder',
    'macro_system.macros',
    'macro_system.profiles',
    'macro_system.detection',
    'macro_system.integration',
    'macro_system.sandbox',
]

a = Analysis(
    [os.path.join(python_dir, 'launcher.py')],
    pathex=[python_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Remove unused modules to reduce size
        'tkinter', 'tk', '_tkinter',
        'matplotlib', 'scipy', 'pandas',
        'IPython', 'notebook', 'jupyter',
        'pytest', 'unittest', 'doctest',
        'numpy.testing', 'numpy.distutils',
        'numpy.f2py', 'numpy.random.tests',
        'http.server',  # Keep email/html - needed by urllib
        'pdb',
        'lib2to3',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HELXAID',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(python_dir, 'UI Icons', 'launcher-icon.ico'),
)
