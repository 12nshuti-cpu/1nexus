"""Local speech-to-text for NEXUS: microphone -> endpointing -> faster-whisper.

Pipeline stages are separate on purpose so each can fail (and be tested) alone:

* :class:`Endpointer`          decides when the user started and stopped talking
                               (pure logic, no audio device needed).
* :class:`MicrophoneRecorder`  captures audio with ``sounddevice`` until the
                               endpointer says stop, or the user finishes/cancels.
* :class:`LocalTranscriber`    turns the audio into text with ``faster-whisper``.

Privacy: the microphone is opened only after an explicit user action, only one
capture can run at a time, and nothing is recorded in the background. Audio is
kept in memory and never written to disk. Transcription runs on this computer;
the only network use is the one-time download of the speech model.
"""
from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SIZE = SAMPLE_RATE * FRAME_MS // 1000  # 480 samples

# Whisper models NEXUS offers. "base" is multilingual and a good speed/accuracy balance.
STT_MODELS = ("tiny", "tiny.en", "base", "base.en", "small", "small.en")
DEFAULT_STT_MODEL = "base"

# Languages the app offers that Whisper cannot recognise are sent as "auto".
_WHISPER_LANGUAGES = {"en", "fr", "sw", "es", "de", "it", "pt"}


class SttError(RuntimeError):
    """A speech-recognition problem with a message that is safe to show the user."""


# ---------------------------------------------------------------------------
# Endpointing
# ---------------------------------------------------------------------------

@dataclass
class EndpointConfig:
    silence_ms: int = 900            # trailing silence that ends an utterance
    min_speech_ms: int = 240         # shorter bursts (clicks, coughs) are ignored
    no_speech_timeout_s: float = 8.0
    max_seconds: float = 30.0
    preroll_ms: int = 300            # audio kept from just before speech was detected
    min_threshold: float = 0.010     # RMS floor so a silent mic is never "speech"
    threshold_ratio: float = 3.0     # speech must be this many times the noise floor
    calibration_ms: int = 300        # initial window used to learn the room's background level
    max_noise_floor: float = 0.03    # cap, so someone who starts talking at once is still heard
    auto_stop: bool = True           # False = push-to-talk: only the user ends the recording


class Endpointer:
    """Energy-based voice-activity detection over fixed-size frames."""

    WAITING, SPEAKING, DONE, TIMEOUT = "waiting", "speaking", "done", "timeout"

    def __init__(self, config: Optional[EndpointConfig] = None):
        self.config = config or EndpointConfig()
        self.state = self.WAITING
        self._noise_floor: Optional[float] = None
        self._preroll: collections.deque = collections.deque(maxlen=max(1, self.config.preroll_ms // FRAME_MS))
        self._frames: list[np.ndarray] = []
        self._speech_frames = 0
        self._silent_run = 0
        self._elapsed_frames = 0
        self._speech_started = False
        self._calibration: list[float] = []

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def rms(frame: np.ndarray) -> float:
        if frame.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))

    @property
    def threshold(self) -> float:
        floor = self._noise_floor if self._noise_floor is not None else 0.0
        return max(self.config.min_threshold, floor * self.config.threshold_ratio)

    @property
    def heard_speech(self) -> bool:
        return self._speech_started

    def audio(self) -> np.ndarray:
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames).astype(np.float32, copy=False)

    # -- main entry ------------------------------------------------------------
    def feed(self, frame: np.ndarray) -> str:
        """Process one frame; returns the current state."""
        if self.state in (self.DONE, self.TIMEOUT):
            return self.state
        frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        level = self.rms(frame)
        self._elapsed_frames += 1
        elapsed_s = self._elapsed_frames * FRAME_MS / 1000.0

        loud = level >= self.threshold

        if not self.config.auto_stop:
            # Push-to-talk: the user decides when to stop, so keep everything and do not
            # depend on voice detection (a quiet speaker must not be discarded).
            self._frames.append(frame)
            if loud:
                self._speech_started = True
            self.state = self.SPEAKING
            if elapsed_s >= self.config.max_seconds:
                self.state = self.DONE
            return self.state

        if not self._speech_started:
            self._preroll.append(frame)
            calibration_frames = max(1, self.config.calibration_ms // FRAME_MS)
            if len(self._calibration) < calibration_frames:
                # Learn the room's background level first, whatever its loudness: a steady
                # fan or street noise must not be mistaken for speech.
                self._calibration.append(level)
                if len(self._calibration) == calibration_frames:
                    floor = float(np.percentile(self._calibration, 20))
                    self._noise_floor = min(floor, self.config.max_noise_floor)
                elif elapsed_s >= self.config.no_speech_timeout_s:
                    self.state = self.TIMEOUT
                return self.state
            if not loud:  # keep tracking slow changes while nobody is talking
                self._noise_floor = 0.9 * (self._noise_floor or 0.0) + 0.1 * min(level, self.config.max_noise_floor)
            loud = level >= self.threshold
            self._speech_frames = self._speech_frames + 1 if loud else 0
            if self._speech_frames * FRAME_MS >= self.config.min_speech_ms:
                self._speech_started = True
                self.state = self.SPEAKING
                self._frames = list(self._preroll)
                self._silent_run = 0
            elif elapsed_s >= self.config.no_speech_timeout_s:
                self.state = self.TIMEOUT
            return self.state

        self._frames.append(frame)
        self._silent_run = 0 if loud else self._silent_run + 1
        if self._silent_run * FRAME_MS >= self.config.silence_ms or elapsed_s >= self.config.max_seconds:
            self.state = self.DONE
        return self.state


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

_MIC_LOCK = threading.Lock()  # one capture at a time -> no duplicate microphone sessions


def list_input_devices() -> list[tuple[int, str]]:
    """(index, name) for every input-capable device; empty if audio cannot be queried."""
    try:
        import sounddevice as sd

        return [
            (index, str(device.get("name", f"Device {index}")))
            for index, device in enumerate(sd.query_devices())
            if device.get("max_input_channels", 0) > 0
        ]
    except Exception:  # noqa: BLE001 - PortAudio errors vary by platform
        return []


def resample(samples: np.ndarray, source_rate: int, target_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Linear-interpolation resampler (adequate for speech recognition)."""
    if source_rate == target_rate or samples.size == 0:
        return samples.astype(np.float32, copy=False)
    duration = samples.size / float(source_rate)
    target_length = max(1, int(round(duration * target_rate)))
    source_positions = np.linspace(0.0, samples.size - 1, num=target_length)
    return np.interp(source_positions, np.arange(samples.size), samples).astype(np.float32)


class MicrophoneRecorder:
    """Capture one utterance. Control it from another thread with finish() / cancel()."""

    def __init__(self, device: Optional[int] = None, config: Optional[EndpointConfig] = None,
                 on_level: Optional[Callable[[float], None]] = None):
        self.device = device
        self.config = config or EndpointConfig()
        self.on_level = on_level
        self._cancel = threading.Event()
        self._finish = threading.Event()

    def cancel(self) -> None:
        """Stop listening and discard the audio."""
        self._cancel.set()

    def finish(self) -> None:
        """Stop listening and keep what was heard (push-to-talk release)."""
        self._finish.set()

    def record(self) -> Optional[np.ndarray]:
        """Block until the utterance ends. Returns 16 kHz mono float32, or None if
        cancelled / nothing was said. Raises :class:`SttError` for device problems."""
        try:
            import sounddevice as sd
        except Exception as error:  # noqa: BLE001
            raise SttError(f"The audio library could not be loaded: {error}") from error

        if not _MIC_LOCK.acquire(blocking=False):
            raise SttError("The microphone is already in use by NEXUS.")
        try:
            return self._record(sd)
        finally:
            _MIC_LOCK.release()

    def _open(self, sd, rate: int, blocksize: int, callback):
        return sd.InputStream(samplerate=rate, channels=1, dtype="float32", blocksize=blocksize,
                              device=self.device, callback=callback)

    def _record(self, sd) -> Optional[np.ndarray]:
        import queue

        blocks: "queue.Queue[np.ndarray]" = queue.Queue()

        def callback(indata, _frames, _time, status):  # runs on the audio thread: keep it tiny
            blocks.put(indata[:, 0].copy())

        rate = SAMPLE_RATE
        try:
            try:
                stream = self._open(sd, rate, FRAME_SIZE, callback)
            except sd.PortAudioError:
                # The device refuses 16 kHz: use its own rate and resample afterwards.
                info = sd.query_devices(self.device, "input")
                rate = int(info["default_samplerate"])
                stream = self._open(sd, rate, int(rate * FRAME_MS / 1000), callback)
        except Exception as error:  # noqa: BLE001
            raise self._friendly(error) from error

        endpointer = Endpointer(self.config)
        pending = np.zeros(0, dtype=np.float32)
        started = time.monotonic()
        hard_limit = self.config.max_seconds + 5.0
        try:
            with stream:
                while not self._cancel.is_set():
                    if time.monotonic() - started > hard_limit:
                        break
                    try:
                        block = blocks.get(timeout=0.1)
                    except queue.Empty:
                        if self._finish.is_set():
                            break
                        continue
                    if rate != SAMPLE_RATE:
                        block = resample(block, rate)
                    pending = np.concatenate([pending, block])
                    state = endpointer.state
                    while pending.size >= FRAME_SIZE and state not in (Endpointer.DONE, Endpointer.TIMEOUT):
                        frame, pending = pending[:FRAME_SIZE], pending[FRAME_SIZE:]
                        state = endpointer.feed(frame)
                        if self.on_level is not None:
                            try:
                                self.on_level(endpointer.rms(frame))
                            except Exception:  # noqa: BLE001
                                pass
                    if state in (Endpointer.DONE, Endpointer.TIMEOUT):
                        break
                    if self._finish.is_set():
                        break
        except Exception as error:  # noqa: BLE001
            raise self._friendly(error) from error

        if self._cancel.is_set():
            return None
        if self.config.auto_stop and not endpointer.heard_speech:
            return None  # silence (timeout) or finished before anyone spoke
        audio = endpointer.audio()
        return audio if audio.size else None

    @staticmethod
    def _friendly(error: Exception) -> SttError:
        text = str(error)
        lowered = text.lower()
        if "no default input" in lowered or "no input" in lowered or "invalid device" in lowered:
            return SttError("No microphone was found. Connect one or pick a different device in Settings.")
        if "permission" in lowered or "access" in lowered or "denied" in lowered:
            return SttError("Windows blocked microphone access. Open Settings > Privacy & security > Microphone "
                            "and allow desktop apps to use it.")
        return SttError(f"The microphone could not be opened: {text}")


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def whisper_language(code: str) -> Optional[str]:
    """Map the app's language choice to a Whisper code, or None to auto-detect."""
    value = (code or "auto").strip().lower()
    return value if value in _WHISPER_LANGUAGES else None


def model_cache_dir() -> Path:
    from config.settings import USER_DATA_DIR

    path = Path(USER_DATA_DIR) / "stt-models"
    path.mkdir(parents=True, exist_ok=True)
    return path


class LocalTranscriber:
    """Loads a faster-whisper model once and reuses it for every utterance."""

    _lock = threading.Lock()
    _models: dict = {}

    def __init__(self, model_name: str = DEFAULT_STT_MODEL, device: str = "cpu", compute_type: str = "int8",
                 model_factory: Optional[Callable] = None, status: Optional[Callable[[str], None]] = None):
        self.model_name = model_name if model_name in STT_MODELS else DEFAULT_STT_MODEL
        self.device = device
        self.compute_type = compute_type
        self._factory = model_factory
        self._status = status

    def _load(self):
        key = (self.model_name, self.device, self.compute_type)
        with self._lock:
            model = self._models.get(key)
            if model is not None:
                return model
            if self._factory is not None:
                factory = self._factory
            else:
                try:
                    from faster_whisper import WhisperModel as factory
                except Exception as error:  # noqa: BLE001
                    raise SttError(f"Speech recognition is not installed (faster-whisper): {error}") from error
            if self._status:
                self._status(f"Loading speech recognition model '{self.model_name}'. "
                             "The first use downloads it and needs an internet connection.")
            try:
                model = factory(self.model_name, device=self.device, compute_type=self.compute_type,
                                download_root=str(model_cache_dir()))
            except Exception as error:  # noqa: BLE001
                raise SttError(self._load_failure(error)) from error
            self._models[key] = model
            return model

    def _load_failure(self, error: Exception) -> str:
        text = f"{type(error).__name__}: {error}"
        lowered = text.lower()
        if any(word in lowered for word in ("connect", "resolve", "offline", "network", "timeout", "hub")):
            return ("The speech recognition model could not be downloaded. Connect to the internet once so NEXUS "
                    "can fetch it, or choose a smaller model in Settings. It works offline afterwards.")
        return f"The speech recognition model could not be loaded: {text[:300]}"

    def transcribe(self, audio: np.ndarray, language: str = "auto") -> tuple[str, str]:
        """Return (text, detected_language). Empty text means nothing intelligible was heard."""
        if audio is None or audio.size < SAMPLE_RATE // 4:
            return "", "auto"
        model = self._load()
        try:
            segments, info = model.transcribe(
                audio.astype(np.float32, copy=False),
                language=whisper_language(language),
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as error:  # noqa: BLE001
            raise SttError(f"Transcription failed: {type(error).__name__}: {str(error)[:200]}") from error
        detected = str(getattr(info, "language", "") or "auto")
        return text, detected

    @classmethod
    def clear_cache(cls) -> None:
        with cls._lock:
            cls._models.clear()
