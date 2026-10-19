# NEXUS Installation Guide

## Windows (Recommended)

1. Install Python 3.11 or 3.12 from python.org (check "Add to PATH").
2. Clone NEXUS:
   ```powershell
   git clone https://github.com/12nshuti-cpu/1nexus.git NEXUS
   cd NEXUS
   ```
3. Create venv and install:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. (Optional local AI) Install Ollama: https://ollama.com → then:
   ```powershell
   ollama pull llama3.1:8b
   ollama create nexus -f models/Modelfile
   ```
5. (Optional local voice) Kokoro:
   ```powershell
   python -m venv .venv-kokoro
   .\.venv-kokoro\Scripts\activate
   pip install kokoro soundfile numpy
   ```
6. Run:
   ```powershell
   .\.venv\Scripts\python app.py
   ```

On first launch, a dialog checks Ollama + models. NEXUS still opens if unavailable; you can use online mode or fix later in Settings.

## Gemini (online) setup

Settings → Gemini API key → paste → Save key & use Gemini. Key saved to `%LOCALAPPDATA%\NEXUS\gemini_api_key.txt`. Alternatively `set GEMINI_API_KEY=AIza...`.

## Startup with Windows

Settings → Start with Windows (creates Run registry entry). Or `Win+R` → `shell:startup`.

## Verifying

- Dashboard shows CPU/Memory/Disk live
- Assistant: type `what time is it` → should answer without AI (tool)
- Reminders: `remind me in 1 minute to test` → check Reminders page
- Voice: toggle VOICE, test mic

## Portable build

See README Packaging. Run `NEXUS.exe` from `dist\NEXUS\` on any Windows PC (no Python needed). User data isolated.

## Uninstall

- Portable: delete `NEXUS` folder
- User data: delete `%LOCALAPPDATA%\NEXUS` (or keep for next install)
- Registry autostart: Settings → disable Start with Windows
