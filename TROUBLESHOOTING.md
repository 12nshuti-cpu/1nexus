# Troubleshooting

## App won't start

- Check Python version: `python --version` → 3.11 or 3.12
- `pip install -r requirements.txt` — watch for errors
- Run with console to see traceback: `python app.py` (not `pythonw`)
- Single instance: close from tray → Exit

## Ollama

- `curl http://127.0.0.1:11434/api/tags` should return JSON
- Firewall: allow Ollama
- `ollama list` → must show `nexus:latest` and `llama3.1:8b`

## No AI response

- Status badge shows ONLINE/LOCAL; check Activity log
- If Gemini 401: key wrong; if 429: quota
- Fallback: set engine to Local in Settings

## Voice

- Mic permission: Windows Settings → Privacy → Microphone
- `sounddevice.query_devices()` must list input devices
- Legacy OpenAI voice disabled by default; use Gemini Live

## Build

- PyInstaller needs `assets/nexus.ico`
- Exclude antivirus false positives by adding `dist` to exclusions
