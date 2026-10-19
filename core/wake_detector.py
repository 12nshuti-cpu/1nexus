from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path


class WakeWordDetector:
    """Local NEXUS wake detector powered by a cached Faster-Whisper tiny model."""

    MODEL_NAME = os.environ.get("NEXUS_WAKE_MODEL", "tiny.en")
    DEVICE = os.environ.get("NEXUS_WAKE_DEVICE", "cpu")
    COMPUTE_TYPE = os.environ.get("NEXUS_WAKE_COMPUTE", "int8")
    WAKE_PHRASES = (
        "hey nexus", "hey nex us", "hey next us", "nexus", "nex us", "next us", "open", "open up"
    )

    _model = None
    _model_lock = threading.Lock()
    _load_error = None

    def __init__(self, on_status=None):
        self.on_status = on_status

    def _status(self, message):
        if callable(self.on_status):
            try:
                self.on_status(str(message))
            except Exception:
                pass

    @classmethod
    def _model_cache_dir(cls):
        base = os.environ.get("LOCALAPPDATA")
        path = Path(base) / "NEXUS" / "wake-models" if base else Path.home() / ".nexus" / "wake-models"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def load(cls, status_callback=None):
        if cls._model is not None:
            return cls._model
        with cls._model_lock:
            if cls._model is not None:
                return cls._model
            if cls._load_error:
                raise RuntimeError(cls._load_error)
            try:
                from faster_whisper import WhisperModel
            except Exception as error:
                cls._load_error = f"Faster-Whisper is unavailable for the local wake detector: {error}"
                raise RuntimeError(cls._load_error) from error
            if callable(status_callback):
                status_callback(f"Preparing local wake detector ({cls.MODEL_NAME}).")
            try:
                cls._model = WhisperModel(
                    cls.MODEL_NAME,
                    device=cls.DEVICE,
                    compute_type=cls.COMPUTE_TYPE,
                    download_root=str(cls._model_cache_dir()),
                    cpu_threads=2,
                    num_workers=1,
                )
            except Exception as error:
                cls._load_error = f"Local wake detector could not load: {error}"
                raise RuntimeError(cls._load_error) from error
            return cls._model

    # Compatibility alias used by older code.
    _load_model = load

    @staticmethod
    def _normalize(text):
        text = str(text or "").lower().strip()
        replacements = {"n e x u s": "nexus", "n e x us": "nex us"}
        for source, target in replacements.items():
            text = text.replace(source, target)
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text)).strip()

    @classmethod
    def contains_wake(cls, text):
        normalized = cls._normalize(text)
        if normalized in ("open", "open up"):
            return True
        if normalized.startswith("open ") or normalized.startswith("open up "):
            return True
        return any(normalized == phrase or normalized.startswith(phrase + " ") for phrase in cls.WAKE_PHRASES[:6])

    @classmethod
    def extract_after_wake(cls, text):
        normalized = cls._normalize(text)
        for prefix in sorted(cls.WAKE_PHRASES[:6], key=len, reverse=True):
            if normalized == prefix:
                return ""
            if normalized.startswith(prefix + " "):
                return normalized[len(prefix):].strip()
        return ""

    def transcribe_locally(self, wav_bytes):
        if not wav_bytes:
            return ""
        model = self.load(self._status)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", prefix="nexus-wake-", delete=False) as file:
                file.write(wav_bytes)
                temp_path = file.name
            segments, _ = model.transcribe(
                temp_path,
                language="en",
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=True,
            )
            return " ".join(str(segment.text or "").strip() for segment in segments).strip()
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def wait_for_wake(self, voice_service, stop_event):
        self.load(self._status)
        while not stop_event.is_set():
            try:
                wav = voice_service.capture_local_speech(
                    wait_timeout=0.8,
                    maximum_recording_time=2.5,
                    end_silence=0.35,
                    cancel_event=stop_event,
                )
            except RuntimeError as error:
                if stop_event.is_set():
                    return None, None
                if "No speech detected" in str(error):
                    continue
                raise
            text = self.transcribe_locally(wav)
            if self.contains_wake(text):
                self._status(f"Wake phrase detected: {text}")
                return text, wav
        return None, None
