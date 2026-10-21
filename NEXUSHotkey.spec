# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the tiny resident Ctrl+Alt+N helper.

One-FILE build on purpose: NEXUS.exe looks for ``NEXUSHotkey.exe`` right next to
itself (app.py), so the helper must run when copied on its own. It only uses the
standard library, so the file stays small.
"""

a = Analysis(
    ['hotkey_helper.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'PySide6', 'PyQt5', 'PyQt6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NEXUSHotkey',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/nexus.ico'],
)
