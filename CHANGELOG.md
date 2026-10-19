# Changelog

## 0.6.0 — 2026-10-19

### Added
- `core/providers.py` — Ollama/Gemini abstraction + ProviderRegistry
- `core/tools.py` — ToolRegistry (15 tools) with validation
- `core/memory.py` — MemoryService (preferences + facts)
- `core/reminders.py` — ReminderService with scheduler
- `core/logger.py` — Rotating file logger
- `core/startup.py` — Greeting + autostart
- `ui/main_window.py` — Reminders & Memory pages, reminder scheduler integration, startup greeting, tray persistence
- `config/settings.py` — version 0.6.0, XDG paths, new defaults (notifications, theme, kokoro)
- Tests: 17 tests (`tests/test_tools.py`, `tests/test_app_startup.py`)
- Docs: README overhaul, INSTALL, TROUBLESHOOTING, PRIVACY, BUILD, AUDIT
- Build: updated NEXUS.spec, scripts/build.ps1, installer/nexus.iss, .env.example, .gitignore

### Fixed
- SystemMonitor cross-platform disk
- Window/keyboard/mouse stub on Linux/macOS
- Kokoro graceful degradation
- Hardcoded paths removal

### Changed
- Version 0.5.0 → 0.6.0
- README now production-grade with quick start, architecture, voice pipeline, packaging

## 0.5.0 — prior

- Settings page + Windows execution upgrade (shell via PowerShell/CMD)
- Gemini hybrid, dependency manager, voice realtime
