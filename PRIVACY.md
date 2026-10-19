# Privacy & Security

- **Local-first**: conversations, reminders, memory stored in `%LOCALAPPDATA%\NEXUS\` SQLite; never auto-uploaded
- **Online**: only when engine=Online/Auto and you have a Gemini key; prompts go to Google; tool requests stay local
- **Mic**: wake detection local (Faster-Whisper tiny); Live audio sent only during mic capture when Gemini configured; no continuous recording
- **Keys**: stored per-user file, not in repo; redacted from logs
- **Shell**: risky commands need confirmation; allowlist for apps
- **Export**: Memory → export_data() JSON; conversations deletable per-item
- **Disable**: Settings → engine=Local + legacy_openai_voice_enabled off for fully offline (minus AI needing Ollama)
