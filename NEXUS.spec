# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('models', 'models'), ('data', 'data'), ('assets', 'assets'), ('config', 'config'), ('ui', 'ui'), ('core', 'core'), ('database', 'database')]
binaries = []
hiddenimports = []
# Collect optional heavy deps if present - graceful fallback if not installed
for pkg in ('faster_whisper', 'ctranslate2', 'onnxruntime'):
    try:
        tmp = collect_all(pkg)
        datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]
    except Exception:
        pass
hiddenimports += [
    'markdown',
    'sounddevice',
    'psutil',
    'requests',
    'websocket',
    'core.providers',
    'core.memory',
    'core.reminders',
    'core.tools',
    'core.logger',
    'core.startup',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NEXUS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/nexus.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NEXUS',
)
