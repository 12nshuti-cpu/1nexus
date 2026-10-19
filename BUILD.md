# Build & Release

## Dev run

```powershell
.\.venv\Scripts\python app.py
pytest tests/ -v
```

## PyInstaller

```powershell
pip install pyinstaller
pyinstaller NEXUS.spec --clean
# dist/NEXUS/NEXUS.exe — test on clean VM
```

Hotkey helper separately:
```powershell
pyinstaller NEXUSHotkey.spec --clean
```

## Inno Setup (Windows)

1. Install Inno Setup 6
2. Edit `installer/nexus.iss` (version from `config/settings.py`)
3. `iscc installer/nexus.iss`

## Release checklist

- [ ] `APP_VERSION` bump in `config/settings.py`
- [ ] `pytest` green
- [ ] Manual smoke: dashboard, chat, reminders, memory, voice toggle
- [ ] Build `dist/NEXUS` and test on fresh Windows (no Python)
- [ ] Tag: `git tag v0.6.0 && git push --tags`
- [ ] GitHub Release: attach installer + portable zip + notes
- [ ] Update README version + changelog

## CI suggestion (.github/workflows/build.yml)

Build on `windows-latest` with Python 3.11, upload artifact.
