# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Bauplan fuer Voice Flow (macOS .app und Windows .exe).

Ziel (Bastian 18.08): "damit es nicht im AppleScript/Python laeuft, sondern
meiner App" — also ein echtes Programm, das ohne Repo-Ordner und ohne venv
startet. Derselbe Bauplan wird auf beiden Plattformen benutzt; die BUNDLE-Sektion
am Ende greift nur auf macOS.

Bauen:  pyinstaller voice-flow.spec --noconfirm
"""
import sys
from pathlib import Path

WURZEL = Path(SPECPATH)

datas = [
    (str(WURZEL / "assets"), "assets"),                       # Modus-Zeichen (Clawd, Chrome)
    (str(WURZEL / "src" / "voice_flow" / "assets"), "voice_flow/assets"),  # Logo/Flocke
    (str(WURZEL / "logo.png"), "."),
]
if (WURZEL / "galvanek_context.txt").exists():
    datas.append((str(WURZEL / "galvanek_context.txt"), "."))

a = Analysis(
    [str(WURZEL / "src" / "voice_flow" / "__main__.py")],
    pathex=[str(WURZEL / "src")],
    binaries=[],
    datas=datas,
    # pynput und pyperclip laden ihre Plattform-Rueckseite dynamisch — ohne
    # diese Eintraege fehlen sie im Bundle und die Hotkeys tun nichts.
    hiddenimports=[
        "pynput.keyboard._darwin", "pynput.mouse._darwin",
        "pynput.keyboard._win32", "pynput.mouse._win32",
        "pyperclip", "voice_flow",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Voice Flow" if sys.platform == "darwin" else "VoiceFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(WURZEL / ("voice-flow.icns" if sys.platform == "darwin"
                       else "src/voice_flow/assets/voice-flow.ico")),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VoiceFlow",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Voice Flow.app",
        icon=str(WURZEL / "voice-flow.icns"),
        bundle_identifier="de.galvanek.voiceflow",
        info_plist={
            "CFBundleName": "Voice Flow",
            "CFBundleDisplayName": "Voice Flow",
            "CFBundleShortVersionString": "0.3.12",
            "CFBundleVersion": "0.3.12",
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            # Ohne diese Texte verweigert macOS Mikrofon und Bildschirmfoto.
            "NSMicrophoneUsageDescription":
                "Voice Flow nimmt dein Diktat über das Mikrofon auf.",
            "NSScreenCaptureUsageDescription":
                "Voice Flow legt deine Screenshots in den Sitzungsordner.",
        },
    )
