# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for NEXUS (one-folder build -> dist/NEXUS/NEXUS.exe).

Build with:  powershell -ExecutionPolicy Bypass -File scripts\\build.ps1
or directly: pyinstaller --noconfirm NEXUS.spec

Rules this file enforces:
* No user data ever goes into the build (the old spec bundled ``data/``, which
  holds a real nexus.db - that must never ship to other people).
* Everything the running app reads from its install folder is listed in ``datas``.
"""
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)  # noqa: F821 - provided by PyInstaller

# Single source of truth for the version: config/settings.py (read as text so the
# build does not import Qt).
_settings_text = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
APP_VERSION = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', _settings_text, re.M).group(1)
_numeric = [int(p) for p in re.findall(r"\d+", APP_VERSION)[:4]]
_numeric += [0] * (4 - len(_numeric))
VERSION_TUPLE = tuple(_numeric)

# Windows "Details" tab metadata. PyInstaller's versioninfo module only imports on
# Windows, so on other platforms (used only for spec checks) it is skipped.
_version_file = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
    )

    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE, mask=0x3F, flags=0x0,
                          OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "NEXUS"),
                StringStruct("FileDescription", "NEXUS desktop AI assistant"),
                StringStruct("FileVersion", APP_VERSION),
                StringStruct("InternalName", "NEXUS"),
                StringStruct("OriginalFilename", "NEXUS.exe"),
                StringStruct("ProductName", "NEXUS"),
                StringStruct("ProductVersion", APP_VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )
    _version_path = ROOT / "build" / "version_info.txt"
    _version_path.parent.mkdir(exist_ok=True)
    _version_path.write_text(str(version_info), encoding="utf-8")
    _version_file = str(_version_path)

datas = [
    ("assets", "assets"),                                  # window/tray icon (app.py resource_path)
    ("models/Modelfile", "models"),                        # local model definition
    ("core/kokoro_tts_worker.py", "core"),                 # run by the *separate* Kokoro Python env
    ("scripts/setup_kokoro.py", "scripts"),                # optional natural-voice installer
    ("scripts/setup_kokoro.ps1", "scripts"),
    ("README.md", "."),
    ("docs", "docs"),
]
binaries = []
hiddenimports = []

# faster-whisper / ctranslate2 ship native libraries and data files.
for package in ("faster_whisper", "ctranslate2"):
    datas += collect_data_files(package)
# keyring selects its backend at runtime, so PyInstaller cannot see it.
hiddenimports += collect_submodules("keyring.backends")
hiddenimports += ["win32ctypes.core"]
# PortAudio for sounddevice.
datas += collect_data_files("_sounddevice_data")

a = Analysis(
    ["app.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "pytest", "torch", "kokoro"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NEXUS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed Qt apps are a common cause of antivirus false positives
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / "assets" / "nexus.ico")],
    version=_version_file,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NEXUS",
)
