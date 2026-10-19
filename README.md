# NEXUS — Personal Digital Command Center

NEXUS is a production-ready desktop AI assistant for Windows, inspired by JARVIS. It combines local AI (Ollama), optional online AI (Google Gemini), voice I/O, PC control, reminders, and persistent memory in a polished PySide6 interface.

**Version:** 0.6.0 · **Author:** NSHUTI Emmanuel · **Branch:** arena/6da65d17-1nexus

![NEXUS](assets/nexus.ico)

---

## Features

### Core
- **Desktop app** with modern HUD dashboard, conversation history, system monitor, activity log
- **Conversation persistence** via SQLite (`%LOCALAPPDATA%\NEXUS\data\nexus.db`)
- **Tool registry**: time/date, calculator, unit converter, web search, file browsing, reminders, memory
- **PC control** (Windows): open apps/websites/folders, window management, keyboard/mouse automation
- **Shell execution**: PowerShell/CMD via allowlist + confirmation gate
- **Reminders**: create/list/complete/delete with background scheduler (persists across restarts while NEXUS runs)
- **Memory**: save/recall/delete user facts; exportable
- **System monitor**: CPU/memory/disk/battery/network — cross-platform safe (no `C:\` hardcode)

### AI
- **Provider abstraction** (`core/providers.py`): `OllamaProvider` + `GeminiProvider` behind one interface
- **Hybrid routing**: `Local` (never cloud), `Online` (cloud when safe), `Automatic` (complex queries → Gemini, Windows tasks stay local)
- **Streaming** for local Ollama; Gemini via `google-genai`
- Secrets never logged; keys stored in `%LOCALAPPDATA%\NEXUS\gemini_api_key.txt` or env vars

### Voice
- **Pipeline**: mic → STT → conversation → response → TTS → playback (each stage independent)
- **STT**: Realtime via Gemini Live (when configured); local Faster-Whisper wake detector for "Hey NEXUS"
- **TTS**: Kokoro via isolated helper (`core/kokoro_tts_worker.py` — model stays loaded once); fallback to Gemini Live audio or silent if unavailable
- Voice can be interrupted; playback cancellable; no overlapping audio

### UI / UX
- Professional dark theme, circular meters, compact header with clock + status badge
- Assistant / System / Activity / Reminders / Memory / Settings as non-modal popups over dashboard
- Greeting uses local time + user name; tray icon with `Ctrl+Alt+N` global hotkey (via `hotkey_helper.py`)
- Responsive: all network/inference/audio off the UI thread (QThread workers)

---

## Architecture

```
app.py                  # Entry, single-instance mutex, tray, dependency check
config/settings.py      # NEXUSSettings (QSettings) + paths (LOCALAPPDATA/XDG)
core/
  providers.py          # AIProvider interface (Ollama/Gemini) + registry
  ai.py                 # Hybrid router (preserved local tool flow)
  gemini_engine.py      # Gemini text + Live adapters
  commands.py           # CommandEngine — PC control + tool shorthand + AI fallback
  tools.py              # ToolRegistry — allowlisted tools with validation
  reminders.py          # ReminderService + scheduler thread
  memory.py             # MemoryService (user_facts, preferences)
  voice.py              # VoiceService (STT/TTS with Kokoro queue)
  kokoro_tts_worker.py  # Persistent Kokoro helper (Python 3.12)
  pc_control.py         # App/website/folder launching
  window_control.py     # Window mgmt (Windows; stub on Linux/macOS)
  system_monitor.py     # Cross-platform telemetry
  startup.py            # Greeting, autostart helpers
database/
  database.py           # SQLite init + WAL + migrations
  models.py             # Conversation/Message dataclasses
ui/
  main_window.py        # MainWindow + dashboard + all pages
  settings_page.py      # Settings form
  styles.py             # DARK_THEME QSS
models/Modelfile        # Ollama Modelfile for `nexus` model
```

---

## Quick Start (Windows)

### Requirements
- **Windows 10/11** 64-bit, 8 GB RAM recommended
- **Python 3.12** (for Kokoro) + **Python 3.11/3.12** for main app (3.11 tested in CI)
- **Ollama** (optional for local AI): https://ollama.com
- **Microphone** (optional, for voice)

### 1. Install

```powershell
git clone https://github.com/12nshuti-cpu/1nexus.git NEXUS
cd NEXUS

# Main environment (Python 3.11 or 3.12)
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# Optional: Kokoro local TTS (requires Python 3.12)
python -m venv .venv-kokoro
.\.venv-kokoro\Scripts\activate
pip install kokoro soundfile numpy
# Model downloads on first use (~300 MB)
```

### 2. Configure Ollama (local AI, offline-capable)

```powershell
# Install Ollama from https://ollama.com, then:
ollama pull llama3.1:8b
ollama create nexus -f models/Modelfile
ollama serve  # keep running
```

`app.py` checks for Ollama at launch: `http://127.0.0.1:11434` (override via `NEXUS_OLLAMA_URL` env).

### 3. Configure Gemini (online, optional)

In NEXUS: **Settings → Gemini API key → paste → Save**. Or set env:

```powershell
$env:GEMINI_API_KEY="AIza..."
# or create %LOCALAPPDATA%\NEXUS\gemini_api_key.txt
```

Gemini text model default: `gemini-2.0-flash` (Settings → Gemini text model).

### 4. Run

```powershell
.\.venv\Scripts\python app.py
# Background/tray mode:
python app.py --background
# Only verify dependencies:
python app.py --setup-dependencies
```

- Window: **Ctrl+Alt+N** (global hotkey) or tray → Open NEXUS
- Close button minimizes to tray; **Exit** from tray menu truly quits

### First-Run Checklist

1. Launch NEXUS — dependency dialog confirms Ollama + models (warnings are okay; app still starts)
2. **Settings** → choose AI Engine: Local / Automatic / Online
3. If Online/Automatic: paste Gemini key, Save, pick model
4. **Microphone test**: Dashboard → 🎤 → speak; check transcription
5. **Voice output**: toggle **VOICE** on; send message → listen
6. **Reminders/Memory**: try `remind me to test in 1 minute` and `remember my name is ...`
7. **PC control**: `open notepad`, `what time is it`, `calculate 12*7`

---

## Voice Pipeline Details

```
Mic capture (sounddevice, VAD) → STT
                                  ├─ Gemini Live (online, needs key) — preferred for mic turns when engine=Online/Auto
                                  └─ Faster-Whisper tiny (local wake only) + offline unavailable notice
→ Conversation (AI provider)
→ Response → TTS
             ├─ Kokoro helper (local, streaming phrases) — if .venv-kokoro present
             ├─ Gemini Live audio (when mic turn used Gemini)
             └─ Silent (voice disabled) — no fake voice
→ Playback (sounddevice RawOutputStream, interruptible)
```

- Kokoro kept alive in separate process; phrases queued so speech starts while AI streams
- `core/voice.py:KokoroSpeechQueue` finds python via `NEXUS_KOKORO_PYTHON` or `.venv-kokoro/{Scripts/python.exe,bin/python}`
- On Python 3.12 main env, uses `sys.executable` directly

**Fallback:** If Kokoro fails, error is shown in activity log; voice toggle still controls Gemini Live turns.

---

## Reminders & Memory

- **Reminders** table: `reminders(id, title, description, due_at, created_at, completed, notified)` — SQLite, indexed
- Parser handles: `in 10 minutes`, `tomorrow at 9am`, `at 14:30`, ISO dates
- Scheduler: background thread polls every 30s; `mark_notified` prevents double-fire; `check_now()` for tests
- **Limitation:** Reminders fire only while NEXUS is running (minimized counts, powered-off does not). Documented in UI.
- **Memory**: `user_memory` (key/value JSON) + `user_facts` (facts). `build_context_snippet()` can inject into system prompt (opt-in future).

UI: **Reminders** and **Memory** pages (tool dialogs) with add/refresh/complete/delete.

---

## Tool System & Safety

All actions via `ToolRegistry` (allowlist):

| Tool | Example |
|---|---|
| `get_time`, `get_date` | `what time is it` |
| `calculate` | `calculate sqrt(16)` |
| `unit_convert` | `5 km to miles` |
| `web_search`, `open_website` | `search for cats`, `open github.com` |
| `list_files`, `read_file` | `list files in Documents` |
| `system_info` | `system info` |
| `create_reminder`, `list_reminders`, `delete_reminder` | `remind me in 5 minutes to drink water` |
| `remember`, `recall` | `remember my dog is Max` |

- Tool arguments validated; `eval` only for math with allowlist
- Shell risky patterns (`rm -rf`, `shutdown`, `Remove-Item C:\*`) require confirmation (Settings → confirm_risky_commands)
- No unrestricted shell for LLM; tool calls are `<NEXUS_TOOL>{...}</NEXUS_TOOL>` only from local Ollama, validated before exec
- Logging via `core/logger.py` → `%LOCALAPPDATA%\NEXUS\logs\nexus.log` (rotating, no secrets)

---

## Packaging & Distribution

### Build Windows executable (on Windows with Python 3.11/3.12)

```powershell
pip install -r requirements-dev.txt
pyinstaller NEXUS.spec --clean --noconfirm
# Output: dist/NEXUS/  (onedir) — contains NEXUS.exe + data
# Test: dist\NEXUS\NEXUS.exe

# Inno Setup installer (optional, if installed):
# iscc installer\nexus.iss  → dist\NEXUS-Setup-0.6.0.exe
```

`NEXUS.spec` bundles `models/`, `data/`, `assets/`, `config/`, `ui/`, `core/`, `database` and collects `faster_whisper`/`ctranslate2`/`onnxruntime` if present.

**Do not bundle large models** — installer is ~150–300 MB; Ollama models download separately (`ollama pull llama3.1:8b`).

### Build script

```powershell
# scripts/build.ps1
.\scripts\build.ps1 -Clean
```

### Data vs install separation

- Install: `C:\Program Files\NEXUS\` (or `dist\NEXUS\` portable)
- User data: `%LOCALAPPDATA%\NEXUS\` (config, logs, db) — survives upgrades
- Never hardcode `C:\Users\clari\...`; use `USER_DATA_DIR` from `config/settings.py`

### Fresh machine test

1. Copy `dist/NEXUS/` to clean Windows VM (no Python)
2. Run `NEXUS.exe` → dependency check warns if Ollama missing but UI still opens
3. Settings → configure; data in new `%LOCALAPPDATA%\NEXUS\`

---

## Configuration

### Paths

| Path | Purpose |
|---|---|
| `%LOCALAPPDATA%\NEXUS\config\` | QSettings (registry on Windows) + settings.json compat |
| `%LOCALAPPDATA%\NEXUS\data\nexus.db` | Conversations, reminders, memory |
| `%LOCALAPPDATA%\NEXUS\logs\nexus.log` | Rotating log |
| `%LOCALAPPDATA%\NEXUS\gemini_api_key.txt` | Gemini key (per-user, 0600 intent) |
| `%LOCALAPPDATA%\NEXUS\wake-models\` | Faster-Whisper tiny cache |

On Linux/macOS: `XDG_DATA_HOME` or `~/.local/share/NEXUS` / `~/.nexus`.

### Env vars (.env.example)

```
NEXUS_OLLAMA_URL=http://127.0.0.1:11434
NEXUS_MODEL=nexus
GEMINI_API_KEY=
NEXUS_KOKORO_PYTHON=
```

---

## Testing

```powershell
# Install dev deps
pip install pytest

# Run (no GUI needed; audio/window tests skip on CI)
pytest tests/ -v

# With coverage:
pip install pytest-cov
pytest --cov=core --cov=database tests/
```

**Covered:**
- App startup, settings load
- Provider availability, system monitor (cross-platform)
- Tool registry, reminders parser + CRUD, memory CRUD
- Conversation manager, database migrations

**Skipped on CI:** PortAudio/mic, window control (stubbed on Linux), GUI.

---

## Security & Privacy

- Keys: never committed; `redact_secrets()` masks `AIza...`, `sk-...`, env assignments before logging/prompt
- Shell: confirmation gate; dangerous patterns regex; `subprocess.run` with timeout, no `shell=True`
- File access: allowlist + blocks `id_rsa`, `.env`, `gemini_api_key`; path traversal not specially needed as absolute paths resolved but sensitive names denied
- Mic: wake detector local only; no continuous upload; explicit consent via Settings (legacy OpenAI voice disabled by default)
- Data: local SQLite only; export via MemoryService.export_data(); online only when user sends message with engine=Online/Auto
- Logs: no prompt content unless explicitly added; rotation 2 MB × 3

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Ollama not running | `ollama serve` in separate terminal; check `http://127.0.0.1:11434/api/tags` |
| `nexus` model missing | `ollama create nexus -f models/Modelfile` |
| Gemini 401/403 | Regenerate key in Google AI Studio; check project API enabled |
| Gemini 429 | Quota/billing; switch engine to Local |
| No mic | Windows → Settings → Privacy → Microphone → allow NEXUS; `Settings → Test mic` in future |
| No voice output | Enable VOICE toggle; check Kokoro `.venv-kokoro` or rely on Gemini Live mic turns |
| Window not appearing | Tray → Open NEXUS; or `Ctrl+Alt+N`; check `hotkey_helper.exe` running |
| Build fails PyInstaller | `pip install pyinstaller`; ensure `assets/nexus.ico` exists; exclude `tkinter` already |

---

## Roadmap

- [ ] Kokoro download wizard (progress bar) instead of manual .venv
- [ ] Reminder OS notifications (Windows toast) + autostart background task via Task Scheduler
- [ ] Document summarize: PDF/DOCX support (currently text only)
- [ ] Multi-language TTS voice picker
- [ ] Export conversations to Markdown/JSON
- [ ] Theme toggle (light) + accent picker

---

## License

MIT — see LICENSE (add your choice). Ollama models have their own licenses; google-genai per Google terms.

---

## Contributing

```powershell
git checkout -b feat/your-feature
pytest -q
# Open PR from feature branch
```

**Maintainer:** NSHUTI Emmanuel — https://github.com/12nshuti-cpu/1nexus

