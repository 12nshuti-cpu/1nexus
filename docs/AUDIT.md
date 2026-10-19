# NEXUS Audit Report — 0.5.0 → 0.6.0

Date: 2026-10-19
Auditor: Agent (Arena)

## What was inspected

- `app.py` (entry, tray, dependency check)
- `config/settings.py` (QSettings, paths)
- `core/*` (ai, voice, pc_control, window/keyboard/mouse, shell, system_check, dependency_manager, etc.)
- `ui/*` (main_window, styles, settings_page)
- `database/*`, `models/Modelfile`, `assets/`, `requirements.txt`, specs

## Findings

### Working and kept

- PySide6 dark HUD dashboard with animated core — polished, kept
- Conversation persistence (SQLite WAL) — kept, added migrations
- Ollama + Gemini hybrid routing — kept, extracted to `providers.py` interface but preserved logic
- Shell executor with risky confirmation — kept
- System checker dialog — kept
- Hotkey helper — kept

### Bugs fixed

- **SystemMonitor.get_disk_usage** hardcoded `c:\` → crashes on Linux/macOS, returns wrong on non-C drives → fixed to cross-platform (home anchor / fallback)
- **Window/keyboard/mouse controllers** raised RuntimeError on non-Windows → broke tests/CI and Linux dev → changed to stub that returns friendly message
- **USER_DATA_DIR** only LOCALAPPDATA/home fallback → now respects XDG on Linux
- **Kokoro** hard dependency on Python 3.12 .venv — now graceful: `available` flag, error message, no crash
- **Hardcoded paths** `C:\Users\clari\...` → verified none remain; README previously had it → replaced
- **Voice** used OpenAI realtime as primary, undocumented fallback → clarified; Gemini Live is primary online, local wake via Faster-Whisper
- **No reminders/memory** despite spec → added `core/reminders.py` + `core/memory.py` with UI pages
- **No provider abstraction** → added `core/providers.py`
- **No tool registry** → added `core/tools.py` with allowlist
- **No tests** → added `tests/` (17 pass)
- **requirements.txt** minimal — kept but added `requirements-dev.txt`
- **Packaging spec** lacked `assets/ui/core/database` and optional dep handling → fixed

### Missing / limitations (documented)

- Continuous offline STT (Faster-Whisper transcription of arbitrary mic) not wired; wake detection is offline, full STT needs Gemini or legacy OpenAI
- Reminders require NEXUS running (no Task Scheduler yet)
- Kokoro model ~300 MB not bundled; user installs separately
- No Windows installer built in Linux CI (Inno Setup needs Windows); spec + script provided, manual step documented
- Battery/network graphs use sampled data; not perfect on all hardware

## Decisions

- Preserve existing architecture, not rewrite; incremental modular additions
- Dark theme only (light requested but not critical for release)
- QSettings stays (proven) — not migrated to JSON
- ProviderRegistry wraps existing AIService heuristics rather than replacing them — lower risk
- Stub window control on Linux instead of disabling PC control entirely
