"""Persistent Kokoro worker (runs inside the separate Kokoro Python environment).

Protocol - one JSON object per line on stdin/stdout:

  start-up  <-  {"ready": true}                       or {"ready": false, "error": "..."}
  request   ->  {"text": "...", "lang": "a", "voice": "af_heart", "speed": 1.0}
  reply     <-  {"ok": true, "path": "<wav file>"}    or {"ok": false, "error": "..."}

The pipeline for each language is created once and reused, so the model is not
reloaded for every phrase. This file must only use the standard library plus
``kokoro``, ``numpy`` and ``soundfile`` (installed by scripts/setup_kokoro.ps1).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
import uuid
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

SAMPLE_RATE = 24000
VOICE_PATTERN = re.compile(r"^[a-z]{2}_[a-z0-9]{2,20}$")
LANG_CODES = {"a", "b", "e", "f", "h", "i", "j", "p", "z"}
MAX_TEXT = 5000


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def to_numpy(audio):
    import numpy as np

    if hasattr(audio, "detach"):  # torch tensor
        audio = audio.detach().cpu().numpy()
    return np.asarray(audio, dtype=np.float32)


def validate(request: dict) -> tuple[str, str, str, float]:
    text = str(request.get("text", "")).strip()
    lang = str(request.get("lang", "a"))
    voice = str(request.get("voice", "af_heart"))
    try:
        speed = float(request.get("speed", 1.0))
    except (TypeError, ValueError):
        speed = 1.0
    if len(text) > MAX_TEXT:
        raise ValueError(f"Text is too long ({len(text)} characters; limit {MAX_TEXT}).")
    if lang not in LANG_CODES:
        raise ValueError(f"Unsupported language code: {lang!r}.")
    if not VOICE_PATTERN.match(voice):
        raise ValueError(f"Invalid voice name: {voice!r}.")
    return text, lang, voice, max(0.5, min(2.0, speed))


def main() -> int:
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except Exception as exc:  # noqa: BLE001
        emit({"ready": False, "error": f"Kokoro imports failed: {exc}"})
        return 2

    root = Path(tempfile.gettempdir()) / "NEXUS" / "kokoro_chunks"
    root.mkdir(parents=True, exist_ok=True)
    pipelines: dict = {}
    emit({"ready": True})

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            text, lang, voice, speed = validate(request)
            if not text:
                emit({"ok": True, "path": ""})
                continue
            if lang not in pipelines:
                pipelines[lang] = KPipeline(lang_code=lang)
            segments = []
            for _graphemes, _phonemes, audio in pipelines[lang](text, voice=voice, speed=speed):
                if audio is not None and len(audio):
                    segments.append(to_numpy(audio))
            if not segments:
                raise RuntimeError("Kokoro produced no audio for this phrase.")
            waveform = segments[0] if len(segments) == 1 else np.concatenate(segments)
            output = root / f"{uuid.uuid4().hex}.wav"
            sf.write(str(output), waveform, SAMPLE_RATE, subtype="PCM_16")
            emit({"ok": True, "path": str(output)})
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(traceback.format_exc())
            sys.stderr.flush()
            emit({"ok": False, "error": str(exc)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
