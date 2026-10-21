"""Tests for core.stt: endpointing on synthetic audio, transcription with a fake model."""
from __future__ import annotations

import numpy as np
import pytest

from core import stt
from core.stt import Endpointer, EndpointConfig, FRAME_SIZE, LocalTranscriber, SttError

RATE = stt.SAMPLE_RATE


def tone(seconds: float, amplitude: float = 0.2) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(seconds: float, level: float = 0.0005) -> np.ndarray:
    rng = np.random.default_rng(1)
    return (level * rng.standard_normal(int(RATE * seconds))).astype(np.float32)


def run(endpointer: Endpointer, audio: np.ndarray) -> str:
    state = endpointer.state
    for start in range(0, audio.size - FRAME_SIZE + 1, FRAME_SIZE):
        state = endpointer.feed(audio[start:start + FRAME_SIZE])
        if state in (Endpointer.DONE, Endpointer.TIMEOUT):
            break
    return state


def test_silence_times_out_without_speech():
    e = Endpointer(EndpointConfig(no_speech_timeout_s=2.0))
    assert run(e, silence(3.0)) == Endpointer.TIMEOUT
    assert not e.heard_speech


def test_speech_then_silence_ends_the_utterance():
    e = Endpointer()
    state = run(e, np.concatenate([silence(0.5), tone(1.0), silence(1.5)]))
    assert state == Endpointer.DONE
    assert e.heard_speech
    captured = e.audio().size / RATE
    assert 1.0 <= captured <= 2.2  # speech + trailing silence + pre-roll, not the whole 3 s


def test_preroll_keeps_the_start_of_the_first_word():
    e = Endpointer()
    run(e, np.concatenate([silence(0.5), tone(0.6), silence(1.2)]))
    assert e.audio().size / RATE >= 0.6 + 0.2  # at least the word plus part of the pre-roll


def test_short_click_is_not_speech():
    e = Endpointer(EndpointConfig(no_speech_timeout_s=2.0))
    assert run(e, np.concatenate([silence(0.3), tone(0.06, 0.5), silence(2.0)])) == Endpointer.TIMEOUT


def test_noisy_room_raises_the_threshold():
    loud_room = silence(1.0, level=0.02)
    e = Endpointer(EndpointConfig(no_speech_timeout_s=4.0))
    run(e, loud_room)
    assert e.threshold > 0.04  # adapted to ~3x the background level
    assert not e.heard_speech  # steady noise alone is not speech


def test_speech_is_still_detected_over_a_steady_noisy_background():
    rng = np.random.default_rng(7)
    noise = lambda secs: (0.02 * rng.standard_normal(int(RATE * secs))).astype(np.float32)  # noqa: E731
    voice = tone(1.0, amplitude=0.3) + noise(1.0)
    e = Endpointer()
    assert run(e, np.concatenate([noise(0.6), voice, noise(1.5)])) == Endpointer.DONE
    assert e.heard_speech


def test_utterance_is_capped_at_max_seconds():
    e = Endpointer(EndpointConfig(max_seconds=2.0))
    assert run(e, tone(5.0)) == Endpointer.DONE
    assert e.audio().size / RATE <= 2.3


def test_push_to_talk_never_stops_on_silence_and_keeps_quiet_speech():
    e = Endpointer(EndpointConfig(auto_stop=False, max_seconds=60))
    quiet = tone(1.0, amplitude=0.004)  # below the speech threshold
    state = run(e, np.concatenate([silence(1.0), quiet, silence(3.0)]))
    assert state == Endpointer.SPEAKING
    assert e.audio().size / RATE == pytest.approx(5.0, abs=0.1)


def test_feeding_after_done_is_ignored():
    e = Endpointer()
    run(e, np.concatenate([tone(0.6), silence(1.5)]))
    size = e.audio().size
    e.feed(tone(0.03))
    assert e.audio().size == size


# ----------------------------------------------------------------- resampling
def test_resample_changes_length_and_keeps_signal():
    source = tone(1.0)
    out = stt.resample(np.repeat(source, 3), 48000)
    assert abs(out.size - RATE) <= 1
    assert out.dtype == np.float32


def test_resample_noop_when_rate_matches():
    audio = tone(0.2)
    assert stt.resample(audio, RATE) is not None and stt.resample(audio, RATE).size == audio.size


# ----------------------------------------------------------------- languages
@pytest.mark.parametrize("code,expected", [("en", "en"), ("fr", "fr"), ("sw", "sw"), ("auto", None), ("rw", None), ("", None), ("EN", "en")])
def test_language_mapping(code, expected):
    assert stt.whisper_language(code) == expected


# --------------------------------------------------------------- transcription
class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, *args, **kwargs):
        FakeModel.created.append((args, kwargs))
        self.calls = []

    created: list = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        return iter([FakeSegment(" hello "), FakeSegment("world ")]), type("Info", (), {"language": "en"})()


@pytest.fixture(autouse=True)
def _fresh_cache():
    LocalTranscriber.clear_cache()
    FakeModel.created = []
    yield
    LocalTranscriber.clear_cache()


def test_transcribe_joins_segments_and_reports_language():
    t = LocalTranscriber("base", model_factory=FakeModel)
    text, language = t.transcribe(tone(1.0), "auto")
    assert (text, language) == ("hello world", "en")


def test_model_is_loaded_once_and_reused():
    t = LocalTranscriber("base", model_factory=FakeModel)
    t.transcribe(tone(1.0))
    t.transcribe(tone(1.0))
    assert len(FakeModel.created) == 1


def test_model_is_cached_in_the_user_data_folder():
    LocalTranscriber("base", model_factory=FakeModel).transcribe(tone(1.0))
    kwargs = FakeModel.created[0][1]
    assert "stt-models" in kwargs["download_root"]


def test_unsupported_language_is_auto_detected():
    t = LocalTranscriber("base", model_factory=FakeModel)
    t.transcribe(tone(1.0), "rw")
    model = next(iter(LocalTranscriber._models.values()))
    assert model.calls[-1]["language"] is None


def test_too_little_audio_returns_nothing_without_loading_a_model():
    t = LocalTranscriber("base", model_factory=FakeModel)
    assert t.transcribe(tone(0.05)) == ("", "auto")
    assert FakeModel.created == []


def test_unknown_model_name_falls_back_to_default():
    assert LocalTranscriber("../../evil").model_name == stt.DEFAULT_STT_MODEL


def test_download_failure_has_a_helpful_message():
    def broken(*_a, **_k):
        raise OSError("Cannot connect to huggingface.co: network unreachable")

    with pytest.raises(SttError, match="internet"):
        LocalTranscriber("base", model_factory=broken).transcribe(tone(1.0))


def test_failure_is_not_cached_so_a_retry_can_succeed():
    attempts = []

    def flaky(*a, **k):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("network down")
        return FakeModel(*a, **k)

    t = LocalTranscriber("base", model_factory=flaky)
    with pytest.raises(SttError):
        t.transcribe(tone(1.0))
    assert t.transcribe(tone(1.0))[0] == "hello world"


def test_transcription_error_is_wrapped():
    class Exploding(FakeModel):
        def transcribe(self, *a, **k):
            raise RuntimeError("decoder crashed")

    with pytest.raises(SttError, match="Transcription failed"):
        LocalTranscriber("base", model_factory=Exploding).transcribe(tone(1.0))


def test_status_message_is_reported_when_loading():
    messages = []
    LocalTranscriber("base", model_factory=FakeModel, status=messages.append).transcribe(tone(1.0))
    assert messages and "first use" in messages[0]


# ------------------------------------------------------------------ recorder
class FakeStream:
    """A sounddevice.InputStream stand-in that feeds scripted audio from a thread."""

    def __init__(self, script, callback, **_kw):
        self.script, self.callback = script, callback
        self._thread = None

    def __enter__(self):
        import threading
        import time

        def pump():
            for start in range(0, self.script.size - FRAME_SIZE + 1, FRAME_SIZE):
                self.callback(self.script[start:start + FRAME_SIZE].reshape(-1, 1), FRAME_SIZE, None, None)
                time.sleep(0.001)

        self._thread = threading.Thread(target=pump, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        return False


class FakeSd:
    class PortAudioError(Exception):
        pass

    def __init__(self, script):
        self.script = script

    def InputStream(self, callback=None, **kw):
        return FakeStream(self.script, callback, **kw)


def test_recorder_returns_the_spoken_audio(monkeypatch):
    sd = FakeSd(np.concatenate([silence(0.4), tone(1.0), silence(1.5)]))
    audio = stt.MicrophoneRecorder()._record(sd)
    assert audio is not None and audio.size / RATE >= 1.0


def test_recorder_returns_none_for_silence():
    sd = FakeSd(silence(2.0))
    recorder = stt.MicrophoneRecorder(config=EndpointConfig(no_speech_timeout_s=1.0))
    assert recorder._record(sd) is None


def test_recorder_cancel_discards_audio():
    sd = FakeSd(tone(10.0))
    recorder = stt.MicrophoneRecorder()
    recorder.cancel()
    assert recorder._record(sd) is None


def test_second_simultaneous_capture_is_refused(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "sounddevice", FakeSd(silence(1.0)))  # CI machines have no PortAudio
    assert stt._MIC_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(SttError, match="already in use"):
            stt.MicrophoneRecorder().record()
    finally:
        stt._MIC_LOCK.release()


def test_device_errors_get_friendly_messages():
    assert "No microphone" in str(stt.MicrophoneRecorder._friendly(RuntimeError("Error querying device -1: no default input")))
    assert "Privacy" in str(stt.MicrophoneRecorder._friendly(RuntimeError("Access denied")))
    assert "could not be opened" in str(stt.MicrophoneRecorder._friendly(RuntimeError("weird")))


def test_settings_roundtrip(settings):
    assert settings.stt_model == "base" and settings.microphone_device is None and settings.push_to_talk is False
    settings.stt_model = "small.en"
    settings.microphone_device = 3
    settings.push_to_talk = True
    assert (settings.stt_model, settings.microphone_device, settings.push_to_talk) == ("small.en", 3, True)
    settings.stt_model = "not-a-model"
    assert settings.stt_model == "base"
    settings.microphone_device = None
    assert settings.microphone_device is None
