# Voice: speaking to NEXUS and hearing it answer

NEXUS has two independent halves, and each can fail without breaking the other:

```
 microphone ──► speech recognition ──► NEXUS (tools, memory, AI) ──► speech synthesis ──► speakers
   (you)          Whisper, on your PC        same as typing            Kokoro / Windows voice
```

## Speaking to NEXUS

Click the microphone button. NEXUS records only while you are listening: a visible **● LISTENING** state
shows it, and nothing is recorded in the background.

| Your AI engine | What the microphone does |
|---|---|
| **Local** | Records, recognises your speech **on your PC** with Whisper, then handles the text exactly as if you had typed it (tools, reminders, memory, the local model) and answers aloud. |
| **Automatic** with no Gemini key | Same as Local. |
| **Automatic** with a Gemini key, or **Online** | Uses **Gemini Live**: your audio is sent to Google, and Gemini produces the spoken answer. Tools such as reminders are *not* available on this path. Choose **Local** if you want voice + tools + privacy. |

Controls while listening:

* **Stop talking** (default): NEXUS finishes when you pause for about a second.
* **Click the microphone again**: finish now and process what was heard.
* **Esc**: cancel; the audio is thrown away.
* **Push-to-talk** (Settings → Speech input → Listening mode): NEXUS does *not* stop on silence; you click the microphone to start and click again when done. Use it in noisy rooms or if you pause a lot.
* Pressing the microphone while NEXUS is speaking stops its speech first, so it does not hear itself.
* Only one microphone session can run at a time.

Spoken requests turn **speech output** on for the rest of the session so you hear the reply; the Voice button
in the header switches it off. This does not change your saved settings.

### Speech-recognition model

First use downloads a Whisper model from Hugging Face (**internet needed once**), then it works offline.

| Model | Download | Notes |
|---|---|---|
| tiny | ~75 MB | Fastest, makes more mistakes |
| **base** (default) | ~145 MB | Good balance, multilingual |
| small | ~480 MB | Most accurate, slower on older CPUs |

`.en` variants are English-only and a little more accurate for English. Whisper supports English, French,
Swahili, Spanish, German, Italian and Portuguese from NEXUS's language list; **Kinyarwanda is not supported by
Whisper**, so that choice falls back to automatic detection and results will be poor. Models are cached in
`%LOCALAPPDATA%\NEXUS\stt-models`.

If recognition fails you get a message in the activity log (no microphone, Windows blocked access, model could
not be downloaded). NEXUS never speaks an error as if it were an answer.

## NEXUS speaking

NEXUS speaks with **Kokoro** when it is installed, and with the **Windows voice** otherwise, or whenever Kokoro
fails. When the fallback is used you are told in the activity log. Settings → **Speech output**:

* *Automatic* (Kokoro, then Windows voice), *Kokoro only* (never switches voices), *Windows voice only*.
* Voice (e.g. `af_heart`) and speed (0.5-2.0).
* The speech queue never overlaps two answers, and the stop control halts playback immediately.

Kokoro keeps its model loaded in a helper process, so it is not reloaded for every sentence. After repeated
failures it pauses for a while and the Windows voice takes over.

### Installing Kokoro (optional)

Why a separate step: the `kokoro` package requires **Python 3.10-3.12** (it does not install on 3.13) and brings in
PyTorch (a large download: roughly 1-2 GB on Windows, an estimate. The Linux test install was 5.9 GB only because Linux wheels bundle CUDA). NEXUS therefore runs Kokoro in its own private Python environment, and the main app is
unaffected.

1. Install Python 3.12 from python.org (tick *py launcher*).
2. Run the setup (also available as a Start-menu shortcut when installed with the installer):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup_kokoro.ps1
   ```

   or, anywhere Python is available: `python scripts/setup_kokoro.py`
   (add `--no-warmup` to skip the voice-model download, `--check` to test an existing install).

   It creates `%LOCALAPPDATA%\NEXUS\kokoro\venv`, installs Kokoro, starts the worker to prove it loads, and
   synthesises a test phrase (downloading the ~330 MB voice model from Hugging Face the first time).
3. Restart NEXUS, then Settings → Speech output → **Automatic** or **Kokoro only**.

If you have no Python 3.10-3.12, the script says so and NEXUS keeps using the Windows voice. The setup changes
nothing outside the Kokoro folder.

## Other voice features

* **Wake word ("Hey NEXUS")** and OpenAI-based background voice are *legacy, opt-in* cloud features (Settings →
  *Allow legacy OpenAI background voice*). They are off by default and not required.
* **Ctrl+Alt+N** global shortcut (Settings → *Global shortcut*) starts a small resident helper so the keys can
  bring NEXUS forward even when it is closed. Off by default.

## Troubleshooting voice

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#voice).
