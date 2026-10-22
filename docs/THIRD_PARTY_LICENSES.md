# Third-party licences

This is an engineering summary, **not legal advice or a complete notice file**. Licence names were read from the
installed package metadata in the test environment. Re-verify them (for example with `pip-licenses`) against the
exact versions you ship, and include each licence's required notice text in a distributed build.

NEXUS itself has no licence yet; choose one before publishing.

## Python packages bundled in the app

| Package | Licence (from metadata) | Note |
|---|---|---|
| PySide6 / Qt for Python | LGPL-3.0 / GPL / commercial | Dynamic linking in a one-folder build is the usual LGPL-friendly way; keep the Qt DLLs replaceable and ship the LGPL text. |
| psutil | BSD-3-Clause | |
| Markdown | BSD-3-Clause | |
| numpy | BSD-type | |
| requests, websocket-client | Apache-2.0 | |
| google-genai | Apache-2.0 | |
| huggingface-hub | Apache-2.0 | |
| sounddevice | MIT | Needs PortAudio, bundled in its wheel; check PortAudio's licence. |
| faster-whisper, ctranslate2 | MIT | |
| onnxruntime | MIT | |
| keyring | MIT | |
| edge-tts | LGPL-3.0 | Natural voice. Imported as an unmodified library; ship the LGPL text and keep it replaceable (one-folder build). Uses Microsoft's Read Aloud service, which has no published terms for third-party use: review before commercial distribution. |
| aiohttp (and its dependencies) | Apache-2.0 / MIT | Pulled in by edge-tts. |
| PyAV | BSD-3-Clause | **Bundles FFmpeg libraries**, which can be LGPL or GPL depending on the build. Review before distributing. |

## Build tools (not shipped, but their output includes a bootloader)

* PyInstaller: GPL-2.0 with a bootloader exception that permits distributing the frozen app under any licence.
* Inno Setup: its own free licence; the installer output has no obligation.

## Optional components downloaded by the user

| Component | Licence | Note |
|---|---|---|
| Kokoro-82M weights and `kokoro` package | Apache-2.0 (believed; confirm on the model card) | Voices; installed on request into the user's profile. PyTorch is BSD-style. `espeak-ng` (GPL-3.0) may be pulled in for phonemes: check what the install actually fetches. |
| OpenAI Whisper weights (via faster-whisper / CTranslate2 conversion) | MIT | Downloaded at first use, not bundled. |
| Llama 3.1 8B (Ollama) | Llama 3.1 Community Licence | Has use and attribution conditions; users download it themselves. |
| Gemini API | Google terms of service | A service, not a bundled component; users supply their own key. |

## Before commercial distribution

1. Generate a full dependency licence report for the frozen build and add the notice texts.
2. Resolve the FFmpeg/PyAV and espeak-ng questions above.
3. Confirm the model licences against the current model cards.
4. Pick a licence for NEXUS and add `LICENSE`.
