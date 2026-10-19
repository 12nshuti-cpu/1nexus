"""Persistent Kokoro worker; run with the project's Python 3.12 .venv-kokoro."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main():
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except Exception as exc:
        emit({"ready": False, "error": f"Kokoro imports failed: {exc}"})
        return 2

    root = Path(tempfile.gettempdir()) / "NEXUS" / "kokoro_chunks"
    root.mkdir(parents=True, exist_ok=True)
    pipelines = {}
    emit({"ready": True})

    for line in sys.stdin:
        try:
            request = json.loads(line)
            text = str(request.get("text", "")).strip()
            lang = str(request.get("lang", "a"))
            voice = str(request.get("voice", "af_heart"))
            if not text:
                emit({"ok": True, "path": ""})
                continue
            if lang not in pipelines:
                pipelines[lang] = KPipeline(lang_code=lang)
            segments = []
            for _graphemes, _phonemes, audio in pipelines[lang](text, voice=voice):
                if audio is not None and len(audio):
                    segments.append(np.asarray(audio, dtype=np.float32))
            if not segments:
                raise RuntimeError("Kokoro produced no audio for this phrase.")
            audio = segments[0] if len(segments) == 1 else np.concatenate(segments)
            output = root / f"{uuid.uuid4().hex}.wav"
            sf.write(str(output), audio, 24000, subtype="PCM_16")
            emit({"ok": True, "path": str(output)})
        except Exception as exc:
            emit({"ok": False, "error": f"{exc}", "trace": traceback.format_exc(limit=2)})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
