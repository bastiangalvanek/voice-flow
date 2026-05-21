# PyInstaller spec for building a single-file Voice Flow EXE.
#
# Usage (from the repo root, with .venv activated):
#   pip install -e ".[build]"
#   python make_icon.py          # one-time: generates voice-flow.ico
#   pyinstaller voice-flow.spec
#   # → dist/voice-flow.exe
#
# Notes:
# - --onefile mode: one large EXE (~80–120 MB) bundling Python + PyQt6 + numpy.
# - --windowed mode: no console window when the EXE runs (it's a tray app).
# - Hidden imports list mirrors the parts pyinstaller misses by default
#   (pystray backend pick, pycaw COM, sounddevice CFFI).
# - Icon is optional — if voice-flow.ico is missing the build still succeeds.

# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None

_ICON_FILE = "voice-flow.ico"
_icon_arg = _ICON_FILE if Path(_ICON_FILE).exists() else None


a = Analysis(
    ['src/voice_flow/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'voice_flow.first_run',
        'pystray._win32',
        'PIL.Image',
        'PIL.ImageDraw',
        'pycaw.pycaw',
        'comtypes.stream',
        'sounddevice',
        '_sounddevice_data',
        'keyboard._winkeyboard',
        'PyQt6.sip',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'pytest',
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
    name='voice-flow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # tray app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_arg,
)
