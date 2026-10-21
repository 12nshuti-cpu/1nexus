# Configuration

Almost everything is in **Settings** (the gear in the app). This page explains each option and where
NEXUS keeps things.

## Where things are stored

| What | Where |
|---|---|
| Conversations, reminders, memories | `%LOCALAPPDATA%\NEXUS\data\nexus.db` (SQLite) |
| Settings | Windows registry, `HKEY_CURRENT_USER\Software\NEXUS\NEXUS` |
| Log file | `%LOCALAPPDATA%\NEXUS\logs\nexus.log` (rotating, 1 MB x 3; secrets are masked) |
| Gemini key | Windows Credential Manager, entry `NEXUS` (plain-text fallback file in `%LOCALAPPDATA%\NEXUS` only if no credential store exists; Settings tells you when that happens) |
| Speech-recognition models | `%LOCALAPPDATA%\NEXUS\stt-models` |
| Kokoro voice environment | `%LOCALAPPDATA%\NEXUS\kokoro\venv` |

The program files (installer location) contain **no** user data, so upgrading or reinstalling does not
touch the above. Set the `NEXUS_DATA_DIR` environment variable to move the data folder.

## Settings reference

**AI engine**

| Setting | Meaning | Default |
|---|---|---|
| AI engine | Local / Online / Automatic (see [INSTALL.md](INSTALL.md#which-mode)) | Automatic |
| Ollama model | Ollama model name | `nexus` |
| Gemini text model | Model used for online text | `gemini-3.8-flash` |
| Fall back to local NEXUS if Gemini fails | Retry on your PC and label the answer | On |
| Gemini API key | Saved to Credential Manager | none |

**Windows commands and tools**

| Setting | Meaning | Default |
|---|---|---|
| Enable shell command execution | Master switch for `run <command>` | On |
| Allow NEXUS AI to use Windows tools | Lets the local model run *read-only* inspection commands from an allow-list | On |
| Default shell | PowerShell or CMD | PowerShell |
| Ask before risky commands | Ask before commands that can change the PC | On (leave it on) |
| Execution timeout / working folder | Limits for commands | 120 s / your user folder |

**Voice**

| Setting | Meaning | Default |
|---|---|---|
| Enable speech output | Read answers aloud. Using the microphone turns this on for the session | Off |
| Voice language | Recognition/reply language hint | Automatic |
| Microphone | Which input device | System default |
| Recognition model | Whisper size: tiny / base / small (and English-only variants) | base |
| Push-to-talk | Off: stops when you pause. On: click the mic to start, click again to stop | Off |
| Speech engine | Automatic (Kokoro then Windows voice) / Kokoro only / Windows voice only | Automatic |
| Kokoro voice, speed | Voice name (e.g. `af_heart`) and 0.5-2.0 | `af_heart`, 1.0 |
| Allow legacy OpenAI background voice and TTS | Old cloud wake-word/TTS path. Needs an OpenAI key. Not needed | Off |

**Privacy, behaviour**

| Setting | Meaning | Default |
|---|---|---|
| Enable memory and personalization | NEXUS only remembers what you explicitly tell it to; switch off to disable all memory | On |
| Include saved memories in online (Gemini) requests | Send saved memories to Gemini with your requests | Off |
| Show a notification when a reminder is due / Speak reminders aloud | How due reminders alert you (speaking also needs speech output on) | On / On |
| Greet me when NEXUS starts | Greeting with your real local time on launch | Off |
| Close to tray | Closing the window keeps NEXUS (and reminders) running in the tray | On |
| Start minimised | Launch hidden in the tray | Off |
| Windows startup | Start NEXUS when you sign in | Off |
| Global shortcut | Ctrl+Alt+N helper that stays resident after NEXUS exits | Off |

**Privacy & data window** (Settings → manage data): view, add, edit and delete reminders and memories;
**Export everything (JSON)**; **Back up database**; **Delete all conversations**.

## Environment variables

NEXUS reads real process environment variables (it does **not** read a `.env` file). See `.env.example`.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `NEXUS_GEMINI_API_KEY` | Gemini key, checked in that order; wins over a saved key |
| `NEXUS_DATA_DIR` | Move the data folder |
| `NEXUS_KOKORO_PYTHON` | Use a specific Python 3.10-3.12 for Kokoro |
| `NEXUS_OLLAMA_URL` | Ollama address (default `http://127.0.0.1:11434`) |
| `NEXUS_MODEL`, `NEXUS_BASE_MODEL` | Local model names |
| `NEXUS_GEMINI_TEXT_MODEL`, `NEXUS_GEMINI_LIVE_MODEL` | Override Gemini models |
| `NEXUS_DISABLE_KEYRING=1` | Testing only: skip the credential store |

## Command-line flags

| Flag | Effect |
|---|---|
| `--background` | Start hidden in the tray |
| `--activate` | Bring the running window to the front (used by the hotkey helper) |
| `--setup-dependencies` | Only check Ollama and the models, print the result and exit |
| `--selftest` | Build the window headlessly, check bundled files, exit `0` on success (used by the build) |
