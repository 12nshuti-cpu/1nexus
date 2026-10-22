"""Speech output: Kokoro preferred, Windows voice fallback, cancellation, cleanup. No audio hardware."""
import subprocess
import threading
import time
from pathlib import Path

import pytest

from core import speech
from core.speech import KokoroError, SpeechManager, WindowsSpeechFallback, clean_for_speech, split_for_speech


class FakeFallback:
    name = "Windows voice"

    def __init__(self, available=True, fail=None):
        self.available = available
        self.fail = fail
        self.spoken = []
        self.stopped = 0

    def speak(self, text, speed=1.0):
        if self.fail:
            raise KokoroError(self.fail)
        self.spoken.append(text)

    def stop(self):
        self.stopped += 1


class FakeHelper:
    """Replaces KokoroHelper (the subprocess wrapper)."""

    behaviour = "ok"   # ok | fail
    instances = []

    def __init__(self, python, helper, log):
        self.requests = []
        self.stopped = False
        FakeHelper.instances.append(self)

    def request(self, payload):
        self.requests.append(payload)
        if FakeHelper.behaviour == "fail":
            raise KokoroError("model file missing")
        return {"ok": True, "path": ""}

    def stop(self):
        self.stopped = True


@pytest.fixture(autouse=True)
def _fake_kokoro(monkeypatch):
    FakeHelper.behaviour = "ok"
    FakeHelper.instances = []
    monkeypatch.setattr(speech, "KokoroHelper", FakeHelper)


def _manager(settings, tmp_path, *, kokoro=True, fallback=None, clock=None):
    py = tmp_path / "python"
    helper = tmp_path / "helper.py"
    py.write_text("")
    helper.write_text("")
    kwargs = dict(
        python_path=py if kokoro else None,
        helper_path=helper if kokoro else None,
        fallback=fallback or FakeFallback(),
        player=lambda path, holder: None,
        log_dir=tmp_path / "logs",
    )
    if clock:
        kwargs["clock"] = clock
    return SpeechManager(settings, **kwargs)


def _drain(manager, timeout=5.0):
    end = time.time() + timeout
    while manager.busy and time.time() < end:
        time.sleep(0.01)
    assert not manager.busy, "speech queue did not finish"


# --------------------------------------------------------------- text shaping
def test_text_cleaned_for_speech():
    spoken = clean_for_speech("## Title\n**Bold** and `code` see https://example.com now")
    assert spoken == "Title Bold and code see a link now"
    assert clean_for_speech("[LOCAL: nexus]\n\nHello") == "Hello"
    assert clean_for_speech("| a | b |\n|---|---|\nDone") == "Done"


def test_long_text_is_split_into_short_phrases():
    parts = split_for_speech("One sentence here. " * 60, max_chars=240)
    assert len(parts) > 3 and all(len(p) <= 240 for p in parts)
    assert split_for_speech("   ") == []


# ------------------------------------------------------------------- engines
def test_kokoro_is_used_when_available(settings, tmp_path):
    m = _manager(settings, tmp_path)
    assert m.enqueue("Hello world.")
    _drain(m)
    assert m.last_engine == "Kokoro" and m.last_error == ""
    assert FakeHelper.instances[0].requests[0]["text"] == "Hello world."
    m.close()


def test_model_is_loaded_once_and_reused_for_every_phrase(settings, tmp_path):
    m = _manager(settings, tmp_path)
    m.enqueue("First sentence. Second sentence. Third sentence.")
    _drain(m)
    assert len(FakeHelper.instances) == 1
    assert len(FakeHelper.instances[0].requests) >= 1
    m.close()


def test_voice_and_speed_come_from_settings(settings, tmp_path):
    settings.kokoro_voice = "af_bella"
    settings.kokoro_speed = 1.25
    m = _manager(settings, tmp_path)
    m.enqueue("Hi.", "en")
    _drain(m)
    payload = FakeHelper.instances[0].requests[0]
    assert payload["voice"] == "af_bella" and payload["speed"] == 1.25
    m.close()


def test_kokoro_failure_falls_back_and_tells_the_user(settings, tmp_path):
    FakeHelper.behaviour = "fail"
    fb = FakeFallback()
    m = _manager(settings, tmp_path, fallback=fb)
    m.enqueue("Hello.")
    _drain(m)
    assert fb.spoken == ["Hello."]
    assert m.last_engine == "Windows voice"
    notice = m.pop_notice()
    assert "Kokoro" in notice and "Windows voice" in notice          # user is informed of the voice change
    m.close()


def test_kokoro_only_setting_never_silently_switches_voice(settings, tmp_path):
    FakeHelper.behaviour = "fail"
    settings.tts_engine = "kokoro"
    fb = FakeFallback()
    m = _manager(settings, tmp_path, fallback=fb)
    m.enqueue("Hello.")
    _drain(m)
    assert fb.spoken == [] and "model file missing" in m.last_error
    m.close()


def test_kokoro_paused_after_repeated_failures_then_retried(settings, tmp_path):
    FakeHelper.behaviour = "fail"
    now = [1000.0]
    m = _manager(settings, tmp_path, clock=lambda: now[0])
    for _ in range(speech.SpeechManager.MAX_KOKORO_FAILURES):
        m.test("Hello.")
    assert not m.kokoro_usable and m.status()["kokoro_cooling_down"]
    now[0] += SpeechManager.KOKORO_COOLDOWN_SECONDS + 1
    assert m.kokoro_usable
    m.close()


def test_windows_voice_alone_when_kokoro_not_installed(settings, tmp_path):
    fb = FakeFallback()
    m = _manager(settings, tmp_path, kokoro=False, fallback=fb)
    assert m.available
    assert m.test("Hello.").engine == "Windows voice" and fb.spoken
    m.close()


def test_no_engine_at_all_reports_false_not_silence(settings, tmp_path):
    m = _manager(settings, tmp_path, kokoro=False, fallback=FakeFallback(available=False))
    assert m.enqueue("Hello.") is False
    assert "No speech engine" in m.last_error
    m.close()


def test_failure_of_every_engine_is_reported(settings, tmp_path):
    fb = FakeFallback(fail="audio device missing")
    m = _manager(settings, tmp_path, kokoro=False, fallback=fb)
    result = m.test("Hello.")
    assert not result.ok and "audio device missing" in result.error
    m.close()


# ------------------------------------------------- cancellation and cleanup
def test_stop_drops_queued_speech_and_stops_playback(settings, tmp_path):
    gate = threading.Event()
    started = threading.Event()

    class SlowFallback(FakeFallback):
        def speak(self, text, speed=1.0):
            started.set()
            gate.wait(5)
            super().speak(text, speed)

    fb = SlowFallback()
    m = _manager(settings, tmp_path, kokoro=False, fallback=fb)
    m.enqueue("One. Two. Three. Four.")
    assert started.wait(5)
    m.stop()
    gate.set()
    _drain(m)
    assert fb.stopped >= 1
    assert len(fb.spoken) <= 1            # whatever was in flight at most; the rest was dropped
    assert not m.speaking
    m.close()


def test_new_speech_after_stop_still_works(settings, tmp_path):
    fb = FakeFallback()
    m = _manager(settings, tmp_path, kokoro=False, fallback=fb)
    m.stop()
    m.enqueue("Again.")
    _drain(m)
    assert fb.spoken == ["Again."]
    m.close()


def test_close_stops_worker_thread_and_helper(settings, tmp_path):
    m = _manager(settings, tmp_path)
    m.enqueue("Hello.")
    _drain(m)
    thread = m._thread
    m.close()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert FakeHelper.instances[0].stopped
    assert not m.available and m.enqueue("late") is False


# ------------------------------------------------------- Windows voice wrapper
class FakeProcess:
    def __init__(self, returncode=0, err=b"", hang=False):
        self.returncode = returncode
        self._err = err
        self._hang = hang
        self.killed = False
        self.sent = None

    def communicate(self, data=None, timeout=None):
        self.sent = data
        if self._hang:
            raise subprocess.TimeoutExpired("ps", timeout)
        return b"", self._err

    def poll(self):
        return None if not self.killed and self._hang else self.returncode

    def kill(self):
        self.killed = True


def test_windows_voice_sends_text_on_stdin_not_in_command_line():
    process = FakeProcess()
    captured = {}

    def runner(cmd, **kwargs):
        captured["cmd"] = cmd
        return process

    voice = WindowsSpeechFallback(runner=runner, powershell="powershell.exe")
    voice.speak("hello; Remove-Item C:\\ -Recurse")          # hostile text must stay data
    assert process.sent == b"hello; Remove-Item C:\\ -Recurse"
    assert not any("Remove-Item" in part for part in captured["cmd"])


def test_windows_voice_failure_and_timeout_raise():
    with pytest.raises(KokoroError, match="failed"):
        WindowsSpeechFallback(runner=lambda *a, **k: FakeProcess(1, b"no voices"), powershell="p").speak("x")
    hung = FakeProcess(hang=True)
    with pytest.raises(KokoroError, match="timed out"):
        WindowsSpeechFallback(runner=lambda *a, **k: hung, powershell="p").speak("x")
    assert hung.killed


def test_windows_voice_unavailable_off_windows():
    voice = WindowsSpeechFallback()
    import os
    if os.name != "nt":
        assert not voice.available
        with pytest.raises(KokoroError):
            voice.speak("x")


# ------------------------------------------------------------ Kokoro worker input
def test_worker_request_validation():
    from core import kokoro_tts_worker as w
    assert w.validate({"text": "Hello", "lang": "a", "voice": "af_heart", "speed": 1.0})[0] == "Hello"
    assert w.validate({"text": "x", "lang": "a", "voice": "af_heart", "speed": 99})[3] == 2.0   # speed is clamped
    assert w.validate({"text": "", "lang": "a", "voice": "af_heart"})[0] == ""                  # empty = nothing to say
    for bad in (
        {"text": "x" * 5001, "lang": "a", "voice": "af_heart", "speed": 1},
        {"text": "x", "lang": "zz", "voice": "af_heart", "speed": 1},
        {"text": "x", "lang": "a", "voice": "../../etc/passwd", "speed": 1},
    ):
        with pytest.raises(Exception):
            w.validate(bad)


# ------------------------------------------------------------ natural voice
class FakeNatural:
    name = "Natural voice"

    def __init__(self, available=True, fail=None, seconds_per_word=0.0):
        self.available = available
        self.fail = fail
        self.seconds_per_word = seconds_per_word
        self.requests = []

    def synthesize(self, text, voice, speed=1.0):
        self.requests.append((text, voice, speed))
        if self.fail:
            raise speech.SpeechError(self.fail)
        words = speech.count_words(text)
        starts = [i * self.seconds_per_word for i in range(words)]
        return speech.Clip(b"\0\0" * 240, 24000, starts)


def _natural_manager(settings, tmp_path, natural, *, kokoro=False, fallback=None, pcm_player=None):
    m = _manager(settings, tmp_path, kokoro=kokoro, fallback=fallback)
    m.natural = natural
    m._pcm_player = pcm_player or (lambda chunks, rate, holder: list(chunks))
    return m


def test_natural_voice_is_tried_first_and_uses_the_chosen_voice(settings, tmp_path):
    settings.natural_voice = "en-US-AndrewMultilingualNeural"
    natural = FakeNatural()
    fb = FakeFallback()
    m = _natural_manager(settings, tmp_path, natural, kokoro=True, fallback=fb)
    m.enqueue("Hello there. How are you?", "en")
    _drain(m)
    assert [r[1] for r in natural.requests] == ["en-US-AndrewMultilingualNeural"] * len(natural.requests)
    assert m.last_engine == "Natural voice" and not fb.spoken and not FakeHelper.instances
    m.close()


def test_other_languages_get_a_native_natural_voice(settings, tmp_path):
    natural = FakeNatural()
    m = _natural_manager(settings, tmp_path, natural)
    m.enqueue("Bonjour.", "fr")
    _drain(m)
    assert natural.requests[0][1] == "fr-FR-VivienneMultilingualNeural"
    m.close()


def test_natural_voice_failure_falls_back_and_says_so(settings, tmp_path):
    natural = FakeNatural(fail="no internet")
    fb = FakeFallback()
    m = _natural_manager(settings, tmp_path, natural, fallback=fb)
    m.enqueue("Hello.")
    _drain(m)
    assert fb.spoken == ["Hello."]
    notice = m.pop_notice()
    assert "no internet" in notice and "Windows voice" in notice
    m.close()


def test_natural_only_setting_never_switches_voice(settings, tmp_path):
    settings.tts_engine = "natural"
    natural = FakeNatural(fail="no internet")
    fb = FakeFallback()
    m = _natural_manager(settings, tmp_path, natural, fallback=fb)
    m.enqueue("Hello.")
    _drain(m)
    assert fb.spoken == [] and "no internet" in m.last_error
    m.close()


def test_natural_voice_paused_after_repeated_failures(settings, tmp_path):
    natural = FakeNatural(fail="offline")
    now = [50.0]
    m = _natural_manager(settings, tmp_path, natural)
    m._clock = lambda: now[0]
    for _ in range(SpeechManager.MAX_NATURAL_FAILURES):
        m.test("Hello.")
    assert not m.natural_usable and m.status()["natural_cooling_down"]
    now[0] += SpeechManager.NATURAL_COOLDOWN_SECONDS + 1
    assert m.natural_usable
    m.close()


def test_progress_follows_the_words_being_spoken(settings, tmp_path):
    playing = threading.Event()
    release = threading.Event()

    def player(chunks, rate, holder):
        playing.set()
        release.wait(5)

    natural = FakeNatural(seconds_per_word=100.0)  # word 1 at once, the rest much later
    m = _natural_manager(settings, tmp_path, natural, pcm_player=player)
    m.enqueue("One two three. Four five.", tag="reply-1")
    assert playing.wait(5)
    assert m.is_speaking("reply-1") and m.spoken_words("reply-1") == 1
    assert m.spoken_words("other") == 0
    release.set()
    _drain(m)
    assert m.spoken_words("reply-1") == 5 and not m.is_speaking("reply-1")
    m.forget("reply-1")
    assert m.spoken_words("reply-1") == 0
    m.close()


def test_stop_ends_progress_for_every_reply(settings, tmp_path):
    playing = threading.Event()
    release = threading.Event()

    def player(chunks, rate, holder):
        playing.set()
        release.wait(5)

    m = _natural_manager(settings, tmp_path, FakeNatural(), pcm_player=player)
    m.enqueue("One. Two. Three.", tag="r")
    assert playing.wait(5)
    m.stop()
    assert not m.is_speaking("r")
    release.set()
    _drain(m)
    m.close()


def test_next_phrase_is_fetched_while_the_current_one_plays(settings, tmp_path):
    seen = []
    release = threading.Event()
    natural = FakeNatural()

    def player(chunks, rate, holder):
        seen.append(len(natural.requests))
        release.wait(2)

    m = _natural_manager(settings, tmp_path, natural, pcm_player=player)
    m.enqueue("A first sentence that is long enough. " * 8)  # several phrases
    deadline = time.time() + 5
    while not seen and time.time() < deadline:
        time.sleep(0.01)
    time.sleep(0.1)
    assert len(natural.requests) >= 2   # the second phrase was requested during the first
    release.set()
    _drain(m)
    assert len(natural.requests) == len(split_for_speech("A first sentence that is long enough. " * 8))
    m.close()


def test_reveal_prefix_follows_spoken_words_in_markdown():
    text = "[LOCAL: nexus]\n\n**Sure!** Here's a link: https://example.com and more.\n\n```\ncode\n```\nDone now."
    assert speech.reveal_prefix(text, 0) == ""
    assert speech.reveal_prefix(text, 1).endswith("**Sure!**")
    assert speech.reveal_prefix(text, 4).endswith("link:")
    assert speech.reveal_prefix(text, 6).endswith("https://example.com")   # spoken as "a link"
    assert speech.reveal_prefix(text, 8).endswith("more.")
    assert speech.reveal_prefix(text, 9).endswith("Done")      # the unspoken code block comes with it
    assert "code" in speech.reveal_prefix(text, 9)
    assert speech.reveal_prefix(text, 99) == text
    assert speech.count_words("- one, two **three**") == 3


def test_natural_voice_rate_and_disabled_by_environment(monkeypatch):
    assert speech.NaturalVoice.rate(1.0) == "+0%" and speech.NaturalVoice.rate(1.25) == "+25%"
    assert speech.NaturalVoice.rate(0.5) == "-50%"
    monkeypatch.setenv("NEXUS_DISABLE_NATURAL_VOICE", "1")
    assert not speech.NaturalVoice().available


def test_natural_voice_settings_are_validated(settings):
    settings.tts_engine = "natural"
    assert settings.tts_engine == "natural"
    settings.natural_voice = "en-GB-SoniaNeural"
    assert settings.natural_voice == "en-GB-SoniaNeural"
    settings.natural_voice = "../../evil"
    assert settings.natural_voice == "en-US-AvaMultilingualNeural"
    assert settings.reveal_text_with_voice is True


def test_first_phrase_can_be_kept_short_so_speech_starts_sooner():
    parts = split_for_speech("Hi there! I can help with that, and I'm ready when you are. Let's go.", first_max=90)
    assert parts[0] == "Hi there!" and len(parts) == 2
    long_first = "Well, the weather in Kigali looks mostly sunny today, with a few clouds and a light breeze later on."
    parts = split_for_speech(long_first, first_max=60)
    assert parts[0].endswith("today,") and " ".join(parts) == long_first
    assert split_for_speech("Short one.", first_max=90) == ["Short one."]
