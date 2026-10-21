# Building and releasing NEXUS

> **Status:** the build scripts, PyInstaller specs and Inno Setup script are written, but the Windows exe and
> installer have **not been built or run** by the author of these scripts (the work was done on Linux).
> Treat everything below as untested on Windows until you complete the checklist at the end and record the
> result in [VERIFICATION.md](VERIFICATION.md). No installer should be handed to users before that.

## Prerequisites (Windows 10/11 64-bit)

* Python 3.11 or 3.12, 64-bit, available as `py` or `python`
* Git
* Optional: [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer

## Build

From the repository root, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

Flags: `-SkipTests` (not recommended for a release), `-SkipInstaller` (app folder only).

The script, in order: creates `.venv-build`, installs `requirements.txt` + `requirements-dev.txt`, runs the
test suite, builds `NEXUS.spec` and `NEXUSHotkey.spec` with PyInstaller (one-folder app, one-file helper,
UPX off), copies the helper beside `NEXUS.exe`, scans `dist\NEXUS` for leaked user data (databases, key files,
`.env`) and fails if any, runs `dist\NEXUS\NEXUS.exe --selftest`, then compiles `installer\nexus.iss` when
`ISCC.exe` is found.

Outputs: `dist\NEXUS\NEXUS.exe` and `installer_output\NEXUS-Setup-<version>.exe`.

The version comes from `APP_VERSION` in `config\settings.py` (single source). Bump it before a release.

### Things the build deliberately does not do

* It does not bundle Ollama, Whisper/Kokoro models, PyTorch or any user data.
* It does not change Windows startup, add scheduled tasks, or install anything outside the user profile.

## Code signing

Unsigned executables trigger SmartScreen and more antivirus false positives. To sign, obtain a code-signing
certificate and run `signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256 ...` on `NEXUS.exe`,
`NEXUSHotkey.exe` and the final `NEXUS-Setup-<version>.exe`. This is not automated here and has not been done.

## Release checklist

1. `git status` is clean; version bumped; `docs/THIRD_PARTY_LICENSES.md` reviewed and a project licence chosen.
2. `pytest` passes on Windows (not only Linux).
3. `build.ps1` completes; `NEXUS.exe --selftest` prints `SELFTEST OK`.
4. Confirm the paths the installer uses exist in the real build: the Inno script copies helper files from
   `_internal\scripts\...`; a Linux build with the same spec confirmed that PyInstaller 6 puts `scripts`, `models`, `assets` and `core\kokoro_tts_worker.py` under `_internal`; confirm the same on Windows.
5. Sign the binaries (optional but recommended). Record SHA-256 of the installer.
6. Run the clean-machine test below and fill in the result.
7. Tag, publish the installer with the hash and the known limitations.

## Clean-machine test plan

Use a fresh Windows 10/11 VM or a spare account **without** Python, Ollama or the source code.

| # | Step | Expected |
|---|---|---|
| 1 | Run the installer as a standard user | No UAC prompt; installs under `%LOCALAPPDATA%\Programs\NEXUS` |
| 2 | Launch from the Start menu | Window opens; first-run wizard appears |
| 3 | Wizard: skip setup | Safe defaults; no startup entry created (check Task Manager → Startup) |
| 4 | Without Ollama or a key, send "hello" | A clear message saying which engine is missing; no crash |
| 5 | Install Ollama and the models per INSTALL.md; Local mode; Test button | Test passes; answers stream |
| 6 | Add a Gemini key; Online mode | Answers from Gemini; key appears in Credential Manager, not in the registry |
| 7 | "remind me to test in 1 minute"; minimise to tray | Alert fires; reminder survives restart |
| 8 | Close the window, then relaunch | Tray keeps it running; second launch focuses the existing one |
| 9 | Click the mic, speak, and let the model download (internet) | Recognised text appears; reply is spoken (Windows voice) |
| 10 | Unplug the network, repeat step 9 | Works offline |
| 11 | Install Kokoro (optional) | `kokoro_worker.log` shows the handshake; speech uses Kokoro; killing the worker falls back to the Windows voice |
| 12 | "delete <test file>" | Confirmation dialog; file lands in the Recycle Bin |
| 13 | Privacy & data → export JSON, delete a memory | Export file valid; memory gone |
| 14 | Uninstall; answer No to data deletion | App removed; `%LOCALAPPDATA%\NEXUS` kept; reinstall sees old conversations |
| 15 | Uninstall; answer Yes | Data folder removed |

Record date, Windows build, pass/fail per step and any screenshots in `docs/VERIFICATION.md`.
