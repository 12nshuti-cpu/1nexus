# NEXUS

NEXUS is a personal AI assistant for Windows. You talk to it by typing or by voice; it answers with a
local model running on your PC (Ollama) or, if you choose, with Google Gemini online. It can set
reminders, remember things you ask it to, do calculations and unit conversions, open apps, folders and
websites, summarise text files, run Windows commands (with confirmation), and read its answers aloud.

> **Project status (v0.5.0).** The source code is tested (see [docs/VERIFICATION.md](docs/VERIFICATION.md)),
> but the Windows `.exe` and installer have **not been built or run yet**: they need a Windows machine.
> The build scripts are included; follow [docs/RELEASE.md](docs/RELEASE.md) and the clean-machine
> checklist there before giving the installer to anyone.

## What you can do

| Area | What works |
|---|---|
| Chat | Text conversations, saved history, new/rename/delete conversations, streaming local answers |
| AI engines | **Local** (Ollama, nothing leaves your PC) · **Online** (Gemini, needs a key) · **Automatic** (local by default, Gemini only for a few request types, and only if a key is set) |
| Voice in | Microphone button → speech recognised **on your PC** with Whisper (Local/Automatic) or Gemini Live (Online). Click-to-stop or push-to-talk, choice of microphone, Esc cancels |
| Voice out | Kokoro neural voice (optional install) with an automatic fallback to the Windows voice. You are told when the fallback is used |
| Reminders | "remind me to call mum in 10 minutes"; list, edit, complete, delete; they survive restarts and fire while NEXUS is in the system tray |
| Memory | "remember that my sister is Aline"; view, edit, delete, or turn personalisation off in **Privacy & data** |
| Everyday tools | time/date, calculator ("calculate 15% of 80"), unit conversion ("convert 10 km to miles"), diagnostics |
| PC control | open apps/folders/sites, window and keyboard shortcuts, file actions (deletes go to the Recycle Bin and ask first), Windows shell via `run <command>` (confirmation required) |
| Documents | `summarize C:\path\notes.txt` or "summarize this document" (file picker). Plain-text formats only (no PDF/Word yet) |
| Your data | Export everything as JSON, back up the database, delete conversations or memories. All stored locally |

"Search for X" opens a Google search in your browser; NEXUS does not fetch and read web pages.

## Install

**With the installer** (once you have built it, see [docs/RELEASE.md](docs/RELEASE.md)): run
`NEXUS-Setup-<version>.exe`. It installs for the current Windows user, no administrator rights needed.
The first launch shows a short setup wizard.

**From source** (developers): see [docs/INSTALL.md](docs/INSTALL.md).

```powershell
git clone https://github.com/12nshuti-cpu/1nexus
cd 1nexus
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

### Requirements

* Windows 10 or 11, 64-bit. (The code is cross-platform Qt, but only Windows is a supported target.)
* **Local AI:** [Ollama](https://ollama.com/download) plus the `llama3.1:8b` model (about 5 GB) and the
  small `nexus` model built from `models/Modelfile`. 8 GB RAM is the practical minimum, 16 GB is comfortable.
  Setup commands are in [docs/INSTALL.md](docs/INSTALL.md).
* **Online AI (optional):** a Gemini API key from Google AI Studio and an internet connection.
* **Voice (optional):** a microphone. First use of speech recognition downloads a Whisper model
  (about 145 MB) once. Kokoro voices are a separate optional install (about 2 GB, needs Python 3.10-3.12);
  see [docs/VOICE.md](docs/VOICE.md).

## Documentation

| | |
|---|---|
| [Installation](docs/INSTALL.md) | Installer, from source, Ollama and Gemini setup |
| [Configuration](docs/CONFIGURATION.md) | Every setting, data locations, environment variables |
| [Voice & Kokoro](docs/VOICE.md) | Speech in/out, push-to-talk, installing Kokoro |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Fixes for the problems people actually hit |
| [Security & privacy](docs/SECURITY_PRIVACY.md) | What is stored, what leaves your PC, how commands are controlled |
| [Release & packaging](docs/RELEASE.md) | Building the exe and installer, release checklist |
| [Third-party licences](docs/THIRD_PARTY_LICENSES.md) | Dependency and model licences to review before distributing |
| [Verification](docs/VERIFICATION.md) | What was tested, what could not be, known limitations |

## Develop

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest            # unit + headless UI tests; no paid services, no microphone needed
.venv\Scripts\python app.py --selftest    # builds the real window headlessly and checks bundled files
powershell -ExecutionPolicy Bypass -File scripts\build.ps1   # exe + installer (Windows)
```

Layout: `app.py` entry point · `ui/` Qt interface · `core/` engine (AI providers, speech, tools,
reminders, memory, shell policy) · `config/` settings · `database/` SQLite · `scripts/` build and Kokoro
setup · `installer/` Inno Setup script · `tests/`.

## Licence

No licence file has been chosen for this repository yet. Add one before publishing or distributing
NEXUS; see [docs/THIRD_PARTY_LICENSES.md](docs/THIRD_PARTY_LICENSES.md) for what your dependencies require.
