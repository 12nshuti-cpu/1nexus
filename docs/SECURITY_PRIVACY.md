# Security and privacy

## What is stored, and where

| Data | Location | Notes |
|---|---|---|
| Conversations, reminders, memories | `%LOCALAPPDATA%\NEXUS\data\nexus.db` (SQLite) | Plain, unencrypted file readable by your Windows account. |
| Settings | Registry `HKCU\Software\NEXUS\NEXUS` | No secrets by design. |
| Gemini API key | Windows Credential Manager (`NEXUS`), via `keyring` | If no credential store is usable, a plain-text fallback file in `%LOCALAPPDATA%\NEXUS\config` is used and the app says so. Or `GEMINI_API_KEY` in the environment. |
| Logs | `%LOCALAPPDATA%\NEXUS\logs` | Keys and bearer tokens are masked before writing. Chat text is not intentionally logged (tool names and outcomes are), but check before sharing a log. |
| Speech models | `%LOCALAPPDATA%\NEXUS\stt-models`, `...\kokoro` | Downloaded on request, not bundled. |
| Voice audio | Not saved | Microphone audio is held in memory only while listening and discarded after recognition or cancel. |

The data folder can be moved with `NEXUS_DATA_DIR`. No keys, usernames or machine paths are in the source;
`.env.example` contains only placeholders and `.env` is git-ignored.

## What can leave your PC

| Feature | Sent to | When |
|---|---|---|
| Local engine (Ollama) | nowhere (localhost) | Always, in Local mode |
| Gemini online / Automatic with key | Google | Your message and recent context for that turn, when the mode routes it there |
| Gemini Live voice | Google | Microphone audio while listening, in Online/Automatic-with-key voice |
| Whisper / Kokoro model download | Hugging Face | Once, when you first use that feature |
| "Search for X", open website | Your browser | You see the page open |
| Legacy OpenAI background voice, wake word | OpenAI | Only if you opt in in Settings |

**Local mode is the only mode where nothing can leave the computer.** Document summaries follow the active
engine, so in Local mode they stay local; in Online mode the file text is sent to Gemini.

NEXUS has no analytics or telemetry.

## You control your data

* **Privacy & data** dialog: view, edit and delete reminders and memories, delete conversations, turn
  personalisation (use of memory/history in answers) off, back up the database, and **export everything as
  JSON**.
* Removing everything: close NEXUS, delete `%LOCALAPPDATA%\NEXUS`, and delete the `NEXUS` entry in Credential
  Manager. The uninstaller offers the folder deletion and asks first.

## Controlling what NEXUS can do

* **No unrestricted shell for the model.** Commands the AI asks to run are checked against an allow-list of
  read-only inspection commands (`Get-Process`, `ipconfig`, ...) with a restricted argument syntax. Pipes
  between listed commands are allowed; `;`, `&`, redirection, sub-expressions, URLs, UNC paths and
  encoded commands are refused. Anything else is declined, and the user is told to type `run <command>`
  themselves (see `core/shell_policy.py`).
* **Commands you type** with `run` go through a confirmation dialog, and risky ones are flagged.
* **File actions** (delete, move, etc.) ask for confirmation first; deletes go to the Recycle Bin. Parsing and
  confirmation are unit-tested; the actual Recycle-Bin move has not been run on Windows yet
  (see [VERIFICATION.md](VERIFICATION.md)).
* **Documents are untrusted.** A summarised file is passed to the model as quoted data in a request with no
  tool access, so instructions hidden inside it cannot trigger actions. Files over 2 MB, binary files, and
  unsupported types are refused.
* The built-in calculator evaluates a small safe grammar, not Python `eval`.
* Shell and Windows-tool features can be switched off in Settings.
* NEXUS never changes Windows startup on its own, never downloads or runs installers/scripts itself (a test
  guards against reintroducing that), and never adds itself to the registry `Run` key without the explicit
  Settings switch.

## Known limitations

* The database and the plain-text key fallback are not encrypted; they rely on Windows account permissions.
  Use full-disk encryption (BitLocker) if the machine can be lost.
* LLM answers can be wrong or manipulated; the safeguards above limit the *actions* a bad answer can trigger, not
  the content of the answer.
* The installer and exe are unsigned until you sign them (see [RELEASE.md](RELEASE.md#code-signing)).
* This is a personal project, not an audited product. No third-party security review has been done.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository, or contact the maintainer directly. Please do not
post exploit details publicly before there is a fix.
