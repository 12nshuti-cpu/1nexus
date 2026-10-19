# NEXUS Settings + Windows Execution upgrade

Update these files in the existing NEXUS project:

- `config/settings.py`
- `core/commands.py`
- `core/ai.py`
- `core/shell_executor.py` (new)
- `core/shell_worker.py` (new)
- `core/voice.py`
- `ui/settings_page.py` (new)
- `ui/main_window.py`

## What changed

### Settings
The existing Settings buttons now open a real Settings page. Settings are persisted in `%LOCALAPPDATA%\\NEXUS\\config\\settings.json`.

The page controls:
- Ollama URL and NEXUS model
- voice enabled/language/TTS configuration
- Windows shell enable/disable
- PowerShell vs Command Prompt default
- shell confirmation behavior
- command timeout
- command working directory
- Windows startup

### Windows execution
NEXUS can execute real Windows commands through CMD or PowerShell.

Examples:

```text
ipconfig /all
Get-Process
powershell Get-Service
cmd tasklist
terminal whoami
run command systeminfo
execute Get-NetIPConfiguration
```

Explicit shell commands are confirmed by default. Disable confirmation in Settings only if you understand that direct shell execution can change the PC.

Shell commands run in a background Qt worker so the NEXUS window remains responsive.

### AI configuration
`core/ai.py` now reloads the saved Ollama URL/model settings for each request, so changing the model in Settings does not require rewriting code.

### Voice configuration
`core/voice.py` keeps the fast realtime transcription model as its realtime path while allowing the saved STT fallback model, TTS model, and TTS voice to be configured from Settings.

## Start

```powershell
cd C:\Users\clari\Documents\NEXUS
python app.py
```

## Hybrid AI and privacy

NEXUS keeps its existing Ollama models (`nexus:latest` based on `llama3.1:8b`) as the local engine. Local text chat, configured local Windows tools, and system actions continue to work without an internet connection when Ollama and the model are installed. Startup only checks for them; it does not install Ollama, pull weights, or rebuild/replace the NEXUS model.

In Settings, choose **Automatic**, **Online**, or **Local**:

- **Local** never sends prompts to Gemini.
- **Automatic** keeps ordinary conversation and Windows/tool requests local; selected complex/current/research prompts use Gemini only when a key is configured. Gemini Live is used for microphone turns when available.
- **Online** sends compatible text requests to Gemini. Windows/system requests remain local because Gemini cannot access NEXUS's local tools. If Gemini fails, the optional fallback setting can retry text locally and labels the answer.

Gemini text and Live voice require internet access, the `google-genai` package (`python -m pip install -r requirements.txt`), and a key. The easiest setup is **Settings → Gemini API key → paste your key → Save key & use Gemini**. This selects Online mode and saves the key for your Windows user under `%LOCALAPPDATA%\NEXUS\gemini_api_key.txt`; alternatively, set `GEMINI_API_KEY` or `GOOGLE_API_KEY`. NEXUS does not display, log, or place the key in conversation history. Gemini usage may be quota-limited or billable according to the Google account/project; configure a key only if you intend to use the cloud route.

Offline voice transcription is not currently available. If Gemini Live is unavailable, NEXUS reports that and directs you to type the request for local processing; it does not silently send microphone audio to a different provider. Cloud voice responses are generated and played by Gemini Live.

The older OpenAI wake-word/background voice and typed-response TTS paths are disabled unless **Allow legacy OpenAI background voice and TTS** is explicitly enabled in Settings and an OpenAI key is configured. This option may incur separate OpenAI quota or charges.
