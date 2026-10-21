# Verification report (v0.5.0)

All work and checks below were done in a Linux cloud sandbox (Python 3.13, PySide6 6.12, headless Qt).
Nothing was run on Windows. This file separates what was checked from what was not.

## Verified

| Area | Evidence |
|---|---|
| Automated tests | `pytest`: **325 passed** (about 14 s), headless, no network, microphone or paid services needed. Covers parsers, reminders, memory, calculator, safe-math, shell policy, PC-control safety, documents, STT endpointing, Kokoro worker protocol, credentials, settings, data export, and headless UI smoke tests. |
| Static check | `pyflakes` run on the non-test code; a few pre-existing unused imports/variables remain in `ui/main_window.py` (harmless, not changed to avoid churn in a 6,000-line file). |
| UI start / shutdown | The headless `MainWindow` builds and closes cleanly, repeated 72 times under load without a crash (after fixing an exit-time crash). |
| Frozen build (Linux only) | `pyinstaller NEXUS.spec` completed and `NEXUS --selftest` on the frozen binary printed `SELFTEST OK`, confirming the spec, the bundled `assets`, `models/Modelfile`, `scripts` and Kokoro worker, and the `_internal` layout the installer assumes. |
| Kokoro worker | Real `kokoro` 0.9.4 installed on Python 3.12 in a private venv; the worker started and answered its handshake; bad requests were rejected and the worker survived; synthesis failed cleanly with an actionable network message (Hugging Face is blocked in the sandbox). |
| Safety | Tests for the shell allow-list, file-delete confirmation, document prompt-injection handling, and a guard test that no download-and-execute code ships. |

## Not verified (could not be done here)

* **Windows exe and installer.** `scripts\build.ps1`, `NEXUSHotkey.spec` and `installer\nexus.iss` have never been
  run. Expect to find and fix small issues on first run. No installer exists.
* **Actual speech.** Kokoro synthesis, Whisper transcription and audio playback could not run (model downloads
  blocked; no audio hardware). Endpointing was tested on synthetic audio only.
* **Real AI providers.** Calls to Ollama and Gemini were tested with fakes and error injection, not live.
* **Windows behaviour.** Recycle Bin deletes, Credential Manager, registry settings, tray, startup toggle,
  global shortcut helper, SmartScreen and antivirus reactions.
* **Real microphones and devices**, and accuracy on real voices or Kinyarwanda (Whisper does not support it).
* **Performance** on low-end hardware, and long-running stability beyond the short loops above.
* **Licence compliance** (see [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)); no legal review.

## Known limitations

* Documents: plain-text formats only; no PDF or Word.
* "Search" opens a browser; NEXUS does not read web pages.
* Gemini Live voice does not use NEXUS tools.
* Reminders alert only while NEXUS is running; missed ones are shown at next launch.
* The database is unencrypted.
* No project licence file yet.
* Legacy files remain in `core/` (`*.backup`) and are untracked or ignored; remove them when satisfied.

## Windows sign-off (to fill in)

Complete the clean-machine plan in [RELEASE.md](RELEASE.md#clean-machine-test-plan) and record: date, Windows
build, installer SHA-256, pass/fail per step.
