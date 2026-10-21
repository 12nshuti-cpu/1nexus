from io import BytesIO
from threading import Lock

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from kokoro import KPipeline

app = FastAPI(title="NEXUS Local Kokoro TTS")

pipeline = None
pipeline_lock = Lock()
generation_lock = Lock()


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    voice: str = "af_heart"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


def get_pipeline():
    global pipeline
    with pipeline_lock:
        if pipeline is None:
            pipeline = KPipeline(lang_code="a")
        return pipeline


@app.get("/health")
def health():
    return {
        "service": "kokoro",
        "status": "ready",
        "model_loaded": pipeline is not None,
        "local_only": True,
    }


@app.post("/tts")
def text_to_speech(request: SpeechRequest):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    if request.voice not in {
        "af_heart", "af_bella", "af_nicole",
        "af_sarah", "af_sky", "am_adam", "am_michael"
    }:
        raise HTTPException(status_code=400, detail="Unsupported voice.")

    try:
        with generation_lock:
            tts = get_pipeline()
            chunks = []

            for _, _, audio in tts(
                text, voice=request.voice, speed=request.speed
            ):
                if audio is not None:
                    chunks.append(audio.detach().cpu().numpy())

            if not chunks:
                raise RuntimeError("Kokoro produced no audio.")

            waveform = np.concatenate(chunks)
            buffer = BytesIO()
            sf.write(buffer, waveform, 24000, format="WAV")

        return Response(
            content=buffer.getvalue(),
            media_type="audio/wav",
            headers={"Cache-Control": "no-store"},
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Local speech generation failed. Check the server terminal."
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
