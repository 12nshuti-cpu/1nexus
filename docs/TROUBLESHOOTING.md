# Troubleshooting

First stop: the **startup diagnostics** panel (it re-runs from the retry button) and the log file
`%LOCALAPPDATA%\NEXUS\logs\nexus.log`. Asking NEXUS for its "diagnostics" runs the built-in diagnostics tool,
a summary of the current configuration (no network calls, no secrets). Logs mask API keys.

## AI engine

| Symptom | Likely cause and fix |
|---|---|
| "Ollama is not running" | Install from <https://ollama.com/download> and start it (it lives in the tray). Or switch to **Online**. |
| "the NEXUS model 'nexus' has not been created yet" | Run `ollama pull llama3.1:8b`, then the `ollama create nexus -f "<Modelfile path>"` command the message shows. `nexus` is built locally; `ollama pull nexus` does not work. |
| First answer is very slow | The model is loading into memory; later answers are faster. A smaller/quantised model or more RAM helps. |
| "Gemini Online mode needs an API key" | Add the key in Settings, or set `GEMINI_API_KEY`. |
| Gemini says quota / rate limit / authentication | Your Google account or key is the cause. NEXUS retries a few times and then reports it. Try again later, check the key, or switch to Local. |
| Answer starts with `[GEMINI UNAVAILABLE: answered locally ...]` | Gemini failed, so the local model answered (the "Fall back to local" setting). |
| NEXUS says it cannot do something | It will not pretend. Check the command list (`help`) and whether *shell command execution* / *Windows tools* are enabled in Settings. |

## Voice

| Symptom | Likely cause and fix |
|---|---|
| "No microphone was found" | Plug one in or pick the device in Settings → Speech input → Microphone. |
| "Windows blocked microphone access" | Windows Settings → Privacy & security → Microphone → allow **desktop apps**. |
| "The microphone is already in use by NEXUS" | A capture is already running; click the mic once to finish or press Esc. Another program holding the device exclusively can also cause errors. |
| "No speech detected" | You were quiet, or the room is very noisy. Speak after the ● LISTENING indicator, move closer, or switch on **Push-to-talk**. |
| Recognition model "could not be downloaded" | The first use needs internet (Hugging Face). Connect once; it works offline afterwards. Corporate proxies/firewalls may block `huggingface.co`. |
| Recognition is inaccurate | Use a bigger model (Settings → Recognition model → small), set the voice language explicitly, use an English-only model for English. Kinyarwanda is not supported by Whisper. |
| Voice replies use a robotic Windows voice | The natural voice needs the internet: check the connection, and that Settings → Speech output → Speech engine is *Automatic* or *Natural voice only*. The activity log says why NEXUS switched. Offline, install Kokoro: see [VOICE.md](VOICE.md#installing-kokoro-optional). |
| The voice starts a couple of seconds after the answer is ready | Normal for the natural voice: it waits about two seconds for the first audio from the service, then speaks without pauses. Kokoro starts faster on a fast PC. |
| I want the whole answer on screen at once | Settings → Speech output → turn off *Words follow the voice*. |
| "No compatible Python found" while installing Kokoro | Kokoro needs Python 3.10-3.12 (not 3.13+). Install Python 3.12 (tick *py launcher*) and run the setup again, or set `NEXUS_KOKORO_PYTHON`. |
| Kokoro setup finished but speech test failed | The voice model downloads from Hugging Face on first use; check the internet connection and re-run `python scripts/setup_kokoro.py`. Details are in `%LOCALAPPDATA%\NEXUS\logs\kokoro_worker.log`. |
| NEXUS hears itself | Don't use speakers at high volume next to the microphone; NEXUS stops speaking when you press the mic, but a loud echo can still be picked up. Headphones fix it. |
| Voice via Gemini cannot set reminders | Gemini Live voice turns don't use NEXUS's tools. Use **Local** (or Automatic without a key) for voice + tools. |

## Reminders and tray

* Reminders only alert **while NEXUS is running**. With *Close to tray* on (default) closing the window keeps
  it running; **Exit NEXUS** from the tray menu really quits. If the PC was off or NEXUS was closed when a
  reminder came due, it is delivered at the next launch and marked as **missed**.
* No tray icon? Some Windows setups hide it in the overflow (^) area. If no tray exists at all, closing the
  window exits NEXUS.

## Installing / starting

| Symptom | Fix |
|---|---|
| SmartScreen warns about the installer | Expected for an unsigned build. See [RELEASE.md](RELEASE.md#code-signing). |
| NEXUS "is already running" | Only one instance runs. Look in the tray; use *Open NEXUS*. |
| Nothing happens on launch | Open `%LOCALAPPDATA%\NEXUS\logs\nexus.log`. Run `NEXUS.exe --selftest` from a terminal: it prints `SELFTEST OK` or the reason it failed. |
| Antivirus quarantines the exe | PyInstaller apps are sometimes flagged. Code signing reduces this; report the false positive to the vendor. |
| Reset everything | Settings → *Reset* restores defaults. To remove all data, delete `%LOCALAPPDATA%\NEXUS` while NEXUS is closed and remove the `NEXUS` entry in Credential Manager. |

## Still stuck?

Collect: NEXUS version (About), Windows version, what you typed or said, and the last lines of `nexus.log`
(secrets are masked, but look before you share), then open an issue at
<https://github.com/12nshuti-cpu/1nexus/issues>.
