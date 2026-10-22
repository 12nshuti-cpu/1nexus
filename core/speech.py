"""Speech output for NEXUS: a natural online voice, Kokoro (local), and the Windows voice.

Engines, in the order *Automatic* tries them
-------------------------------------------
1. **Natural voice**: Microsoft's neural voices (the ones behind Edge's Read Aloud) through
   the ``edge-tts`` package. They sound like a person talking, need no key, and report when
   each word is spoken, so the chat can show the words as they are said. The spoken text is
   sent to Microsoft, so it needs the internet.
2. **Kokoro**: a neural voice that runs on this PC (installed separately, see below).
3. **Windows voice**: the built-in SAPI voice. Always there, but sounds robotic.

Kokoro: why a separate process
----------------------
Kokoro and its PyTorch dependencies support a narrower range of Python
versions than the rest of the app. NEXUS therefore runs Kokoro in a *separate
Python environment* (see ``scripts/setup_kokoro.ps1``) and talks to a small
long-lived helper (``kokoro_tts_worker.py``) over stdin/stdout JSON lines. The
model is loaded once and reused for every phrase. The helper's Python can live
anywhere; it is looked for in, in order:

1. the ``NEXUS_KOKORO_PYTHON`` environment variable,
2. ``<user data>/kokoro/venv`` (what the setup script creates),
3. ``<install folder>/kokoro/venv`` and the legacy ``<project>/.venv-kokoro``.

Behaviour guarantees
--------------------
* Nothing here touches the UI thread - callers only enqueue text.
* Playback can be cancelled at any time (:meth:`SpeechManager.stop`).
* If an engine is missing or keeps failing, the next one is used and the user
  is *told* (:meth:`SpeechManager.pop_notice`); it never switches silently.
  After repeated failures an engine is not retried for a while.
* :meth:`SpeechManager.spoken_words` says how far into a reply the voice has got,
  so the interface can reveal the text in step with the speech.
* Error text is never spoken as if it were an answer.
"""
from __future__ import annotations

import asyncio
import bisect
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from core.logger import get_logger

log = get_logger("speech")

LANGUAGE_VOICES = {
    "auto": ("a", "af_heart"),
    "en": ("a", "af_heart"),
    "fr": ("f", "ff_siwis"),
    "es": ("e", "ef_dora"),
    "it": ("i", "if_sara"),
    "pt": ("p", "pf_dora"),
}
# Voices NEXUS offers for English (Kokoro American-English set).
ENGLISH_VOICES = (
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_michael", "am_echo",
)

# Microsoft neural voices for the natural engine. English uses the voice chosen in Settings.
NATURAL_LANGUAGE_VOICES = {
    "fr": "fr-FR-VivienneMultilingualNeural",
    "es": "es-ES-ElviraNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "de": "de-DE-SeraphinaMultilingualNeural",
    "sw": "sw-KE-ZuriNeural",
}
DEFAULT_NATURAL_VOICE = "en-US-AvaMultilingualNeural"
# (voice id, label) offered in Settings for English replies.
NATURAL_ENGLISH_VOICES = (
    ("en-US-AvaMultilingualNeural", "Ava (warm, expressive)"),
    ("en-US-AndrewMultilingualNeural", "Andrew (warm, confident)"),
    ("en-US-EmmaMultilingualNeural", "Emma (cheerful, clear)"),
    ("en-US-BrianMultilingualNeural", "Brian (relaxed, casual)"),
    ("en-GB-SoniaNeural", "Sonia (British)"),
    ("en-GB-RyanNeural", "Ryan (British)"),
    ("en-KE-AsiliaNeural", "Asilia (Kenyan English)"),
    ("en-KE-ChilembaNeural", "Chilemba (Kenyan English)"),
)
NATURAL_SAMPLE_RATE = 24000
# Speaking pace used to estimate word timing when an engine does not report it.
_WORDS_PER_SECOND = 2.6

_TAG_LINE = re.compile(r"^\s*\[(?:LOCAL|GEMINI|ONLINE)[^\]\n]*\]\s*", re.IGNORECASE)


def clean_for_speech(text: str) -> str:
    """Strip markdown and NEXUS routing tags so only natural prose is spoken."""
    value = str(text or "")
    value = _TAG_LINE.sub("", value)
    value = re.sub(r"```[\s\S]*?```", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"(?:https?://|www\.)\S+", "a link", value)  # never read a URL out character by character
    value = re.sub(r"^\s*\|.*\|\s*$", " ", value, flags=re.MULTILINE)  # tables are not speakable
    value = re.sub(r"#{1,6}\s*", "", value)
    value = re.sub(r"[*_~`]+", "", value)
    value = re.sub(r"^\s*[-+•]\s+", "", value, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", value).strip()


def split_for_speech(text: str, max_chars: int = 240, first_max: int | None = None) -> list[str]:
    """Split into phrase-sized chunks so playback starts quickly.

    With ``first_max`` the first chunk is just the opening sentence (at most that long), so
    the voice can start while the rest is still being prepared.
    """
    value = clean_for_speech(text)
    if not value:
        return []
    sentences = re.split(r"(?<=[.!?…])\s+", value)
    chunks: list[str] = []
    if first_max and (len(sentences) > 1 or len(sentences[0]) > first_max):
        first = sentences.pop(0)
        if len(first) > first_max:
            cut = first.rfind(", ", 0, first_max) + 1  # a pause at a comma sounds natural
            if cut <= 20:
                cut = first.rfind(" ", 0, first_max)
            cut = cut if cut > 20 else first_max
            sentences.insert(0, first[cut:].strip())
            first = first[:cut].strip()
        chunks.append(first)
    current = ""
    for sentence in sentences:
        while len(sentence) > max_chars:  # very long run-on: cut at a space
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 40 else max_chars
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return [c for c in chunks if c]


_WORD = re.compile(r"\S+")
_URL = re.compile(r"(?:https?://|www\.)\S+")
_UNSPOKEN_BLOCK = re.compile(r"```[\s\S]*?(?:```|\Z)|^[ \t]*\|.*\|[ \t]*$", re.MULTILINE)


def count_words(text: str) -> int:
    """Words as NEXUS counts them for pacing: whitespace-separated runs with a letter or digit."""
    return sum(1 for token in _WORD.findall(str(text or "")) if any(c.isalnum() for c in token))


def reveal_prefix(text: str, words: int) -> str:
    """The start of ``text`` (markdown, as displayed) covering its first ``words`` spoken words.

    Counting follows :func:`clean_for_speech`: code blocks and tables are not spoken, so they
    appear with the next spoken word; a URL is spoken as "a link" (two words).
    """
    value = str(text or "")
    if words <= 0:
        return ""
    tag = _TAG_LINE.match(value)
    start = tag.end() if tag else 0
    unspoken = [(m.start(), m.end()) for m in _UNSPOKEN_BLOCK.finditer(value, start)]
    spoken = 0
    end = start
    for token in _WORD.finditer(value, start):
        word = token.group()
        if not any(c.isalnum() for c in word) or any(a <= token.start() < b for a, b in unspoken):
            continue
        if spoken >= words:
            return value[:end]
        spoken += 2 if _URL.match(word) else 1
        end = token.end()
    return value  # the voice has reached the end of what is shown


# --------------------------------------------------------------------------
# Locating the Kokoro runtime
# --------------------------------------------------------------------------

def kokoro_env_dir() -> Path:
    from config.settings import USER_DATA_DIR

    return Path(USER_DATA_DIR) / "kokoro"


def _venv_python(venv: Path) -> Path | None:
    for rel in (("Scripts", "python.exe"), ("bin", "python")):
        candidate = venv.joinpath(*rel)
        if candidate.is_file():
            return candidate
    return None


def resource_root() -> Path:
    from config.settings import RESOURCE_ROOT

    return Path(RESOURCE_ROOT)


def find_kokoro_python(project_root: Path | None = None) -> Path | None:
    override = os.environ.get("NEXUS_KOKORO_PYTHON")
    if override and Path(override).is_file():
        return Path(override)
    roots = [kokoro_env_dir() / "venv"]
    install_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
    if install_dir is not None:
        roots.append(install_dir / "kokoro" / "venv")
    root = Path(project_root) if project_root else resource_root()
    roots += [root / "kokoro" / "venv", root / ".venv-kokoro"]
    for venv in roots:
        found = _venv_python(venv)
        if found:
            return found
    return None


def find_kokoro_helper() -> Path | None:
    here = Path(__file__).resolve().with_name("kokoro_tts_worker.py")
    candidates = [here, resource_root() / "helpers" / "kokoro_tts_worker.py", resource_root() / "core" / "kokoro_tts_worker.py"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _no_window_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


# --------------------------------------------------------------------------
# Kokoro helper process
# --------------------------------------------------------------------------

class SpeechError(RuntimeError):
    pass


class KokoroError(SpeechError):
    pass


class KokoroHelper:
    """A persistent Kokoro worker process speaking JSON lines."""

    def __init__(
        self,
        python: Path,
        script: Path,
        log_path: Path | None = None,
        startup_timeout: float = 300.0,   # first start may load a model from disk
        request_timeout: float = 90.0,
    ):
        self.python = Path(python)
        self.script = Path(script)
        self.log_path = log_path
        self.startup_timeout = startup_timeout
        self.request_timeout = request_timeout
        self._process: subprocess.Popen | None = None
        self._lines: "queue.Queue[Optional[str]]" = queue.Queue()
        self._stderr_handle = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _read_stdout(self, process: subprocess.Popen) -> None:
        try:
            for line in process.stdout:  # type: ignore[union-attr]
                self._lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            self._lines.put(None)  # EOF marker

    def _next_line(self, timeout: float) -> str:
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            raise KokoroError(f"Kokoro did not answer within {int(timeout)} seconds.") from None
        if line is None:
            raise KokoroError("The Kokoro helper stopped unexpectedly. See the NEXUS log for details.")
        return line

    def _next_message(self, timeout: float) -> dict:
        """Next JSON object from the worker. Stray non-JSON lines (library warnings) are skipped."""
        deadline = time.monotonic() + timeout
        while True:
            line = self._next_line(max(0.05, deadline - time.monotonic()))
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                if time.monotonic() >= deadline:
                    raise KokoroError("Kokoro did not answer in time.") from None
                continue
            if isinstance(message, dict):
                return message

    def start(self) -> None:
        if self.running:
            return
        self.stop()
        self._lines = queue.Queue()
        stderr = subprocess.DEVNULL
        if self.log_path is not None:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                self._stderr_handle = open(self.log_path, "ab")
                stderr = self._stderr_handle
            except OSError:
                self._stderr_handle = None
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", HF_HUB_DISABLE_PROGRESS_BARS="1")
        process = subprocess.Popen(
            [str(self.python), str(self.script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
            creationflags=_no_window_flags(),
        )
        self._process = process
        threading.Thread(target=self._read_stdout, args=(process,), name="NEXUS-Kokoro-reader", daemon=True).start()
        try:
            status = self._next_message(self.startup_timeout)
        except KokoroError:
            self.stop()
            raise
        if not status.get("ready"):
            self.stop()
            raise KokoroError(str(status.get("error") or "Kokoro could not start."))

    def request(self, payload: dict) -> dict:
        self.start()
        process = self._process
        assert process is not None and process.stdin is not None
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
            reply = self._next_message(self.request_timeout)
        except (OSError, ValueError, KokoroError) as error:
            self.stop()
            if isinstance(error, KokoroError):
                raise
            raise KokoroError(f"Kokoro helper communication failed: {error}") from error
        if not reply.get("ok"):
            raise KokoroError(str(reply.get("error") or "Kokoro synthesis failed."))
        return reply

    def stop(self) -> None:
        process, self._process = self._process, None
        if process is not None:
            try:
                if process.stdin:
                    process.stdin.close()
            except OSError:
                pass
            try:
                process.terminate()
                process.wait(timeout=2.0)
            except Exception:  # noqa: BLE001
                try:
                    process.kill()
                except Exception:  # noqa: BLE001
                    pass
        if self._stderr_handle is not None:
            try:
                self._stderr_handle.close()
            except OSError:
                pass
            self._stderr_handle = None


# --------------------------------------------------------------------------
# Natural voice (Microsoft neural voices via edge-tts)
# --------------------------------------------------------------------------

@dataclass
class Clip:
    """Decoded speech: 16-bit mono PCM plus the time (seconds) each word starts."""

    pcm: bytes
    rate: int
    word_starts: list

    @property
    def duration(self) -> float:
        return len(self.pcm) / 2 / max(1, self.rate)


class Mp3Decoder:
    """Turns MP3 bytes into 16-bit mono PCM as they arrive (PyAV, already installed for speech recognition)."""

    def __init__(self, rate: int = NATURAL_SAMPLE_RATE):
        import av

        self._codec = av.CodecContext.create("mp3", "r")
        self._resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)

    def _pcm(self, frames) -> bytes:
        pcm = bytearray()
        for frame in frames:
            for out in self._resampler.resample(frame):
                pcm += bytes(out.planes[0])[: out.samples * 2]
        return bytes(pcm)

    def feed(self, data: bytes) -> bytes:
        frames = []
        for packet in self._codec.parse(data):
            frames.extend(self._codec.decode(packet))
        return self._pcm(frames)

    def flush(self) -> bytes:
        frames = []
        for packet in self._codec.parse(None):
            frames.extend(self._codec.decode(packet))
        frames.extend(self._codec.decode(None))
        pcm = self._pcm(frames)
        tail = bytearray()
        for out in self._resampler.resample(None):
            tail += bytes(out.planes[0])[: out.samples * 2]
        return pcm + bytes(tail)


class NaturalVoice:
    """Microsoft's online neural voices. Free and keyless, but the text goes to Microsoft."""

    name = "Natural voice"
    TIMEOUT_SECONDS = 30.0

    @property
    def available(self) -> bool:
        if os.environ.get("NEXUS_DISABLE_NATURAL_VOICE"):
            return False
        try:
            import av  # noqa: F401
            import edge_tts  # noqa: F401
        except Exception:  # noqa: BLE001 - a missing optional package just means "not available"
            return False
        return True

    def warm_up(self) -> None:
        """Load the voice libraries ahead of the first reply (about a second on a typical PC)."""
        if not self.available:
            return
        try:
            import ssl

            import aiohttp  # noqa: F401
            import av  # noqa: F401
            import edge_tts  # noqa: F401

            ssl.create_default_context()
        except Exception:  # noqa: BLE001 - only an optimisation
            pass

    @staticmethod
    def rate(speed: float) -> str:
        return f"{round((float(speed) - 1.0) * 100):+d}%"

    def stream(
        self, text: str, voice: str, speed: float, on_pcm: Callable[[bytes], None], on_word: Callable[[float], None]
    ) -> None:
        """Fetch speech, handing over PCM and word start times (seconds) as they arrive."""
        import edge_tts

        decoder = Mp3Decoder()
        received = False

        async def fetch() -> None:
            nonlocal received
            communicate = edge_tts.Communicate(text, voice, rate=self.rate(speed), boundary="WordBoundary")
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    received = True
                    pcm = decoder.feed(chunk["data"])
                    if pcm:
                        on_pcm(pcm)
                elif chunk.get("type") == "WordBoundary":
                    on_word(float(chunk.get("offset", 0)) / 1e7)  # 100-ns units

        try:
            asyncio.run(asyncio.wait_for(fetch(), self.TIMEOUT_SECONDS))
        except asyncio.TimeoutError:
            raise SpeechError("the natural voice service did not answer in time") from None
        except Exception as error:  # noqa: BLE001 - network, DNS, service changes
            detail = str(error) or type(error).__name__
            raise SpeechError(f"could not reach the natural voice service: {detail[:160]}") from error
        if not received:
            raise SpeechError("the natural voice service returned no audio")
        tail = decoder.flush()
        if tail:
            on_pcm(tail)

    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> Clip:
        """The whole phrase at once (for callers that do not need streaming)."""
        pcm = bytearray()
        starts: list = []
        self.stream(text, voice, speed, pcm.extend, starts.append)
        return Clip(bytes(pcm), NATURAL_SAMPLE_RATE, starts)


class NaturalSpeechJob:
    """One phrase being fetched in the background; its audio can be played while it arrives."""

    def __init__(self, natural, text: str, voice: str, speed: float):
        self.chunks: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self.word_starts: list = []
        self.error: Exception | None = None
        self.rate = NATURAL_SAMPLE_RATE
        self._natural = natural
        self._args = (text, voice, speed)
        self.thread = threading.Thread(target=self._run, name="NEXUS-Speech-fetch", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        try:
            stream = getattr(self._natural, "stream", None)
            if callable(stream):
                stream(*self._args, self.chunks.put, self.word_starts.append)
            else:
                clip = self._natural.synthesize(*self._args)
                self.rate = clip.rate
                self.word_starts.extend(clip.word_starts)
                self.chunks.put(clip.pcm)
        except Exception as error:  # noqa: BLE001 - reported by whoever plays the job
            self.error = error
        finally:
            self.chunks.put(None)

    def next_chunk(self, timeout: float) -> Optional[bytes]:
        try:
            return self.chunks.get(timeout=timeout)
        except queue.Empty:
            raise SpeechError("the natural voice service stopped sending audio") from None


def play_pcm(chunks, rate: int, stream_holder: list) -> None:
    """Play 16-bit mono PCM chunks through sounddevice as they come; ``stream_holder`` lets stop() abort it."""
    import sounddevice as sd

    with sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16", blocksize=2048) as stream:
        stream_holder.append(stream)
        try:
            for chunk in chunks:
                stream.write(chunk)
        finally:
            if stream_holder:
                stream_holder.clear()


# --------------------------------------------------------------------------
# Windows system voice (fallback)
# --------------------------------------------------------------------------

_PS_SPEAK = (
    "[Console]::InputEncoding=[System.Text.Encoding]::UTF8;"
    "Add-Type -AssemblyName System.Speech;"
    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "$s.Rate={rate};"
    "$t=[Console]::In.ReadToEnd();"
    "$s.Speak($t);$s.Dispose()"
)


class WindowsSpeechFallback:
    """Speaks through the built-in Windows (SAPI) voices. No extra install."""

    name = "Windows voice"

    def __init__(self, runner: Callable[..., subprocess.Popen] | None = None, powershell: str | None = None):
        self._runner = runner or subprocess.Popen
        self._powershell = powershell
        self._process: subprocess.Popen | None = None
        self._cancelled: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _find_powershell(self) -> str | None:
        if self._powershell:
            return self._powershell
        if os.name != "nt":
            return None
        root = os.environ.get("SystemRoot", r"C:\Windows")
        candidate = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        return str(candidate) if candidate.is_file() else shutil.which("powershell")

    @property
    def available(self) -> bool:
        return self._find_powershell() is not None

    def speak(self, text: str, speed: float = 1.0) -> None:
        shell = self._find_powershell()
        if shell is None:
            raise KokoroError("The Windows voice is only available on Windows.")
        rate = max(-10, min(10, round((float(speed) - 1.0) * 10)))
        command = _PS_SPEAK.format(rate=rate)
        with self._lock:
            process = self._runner(
                [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=_no_window_flags(),
            )
            self._process = process
        try:
            _out, err = process.communicate(text.encode("utf-8"), timeout=120)
        except subprocess.TimeoutExpired:
            process.kill()
            raise KokoroError("The Windows voice timed out.") from None
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None
        with self._lock:
            cancelled = self._cancelled is process
            if cancelled:
                self._cancelled = None
        if cancelled:
            return  # the user stopped playback; not an error
        if process.returncode not in (0, None):
            detail = (err or b"").decode("utf-8", "replace").strip()
            raise KokoroError(f"Windows voice failed: {detail[:200]}")

    def stop(self) -> None:
        with self._lock:
            process = self._process
            if process is not None and process.poll() is None:
                self._cancelled = process
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------
# Manager
# --------------------------------------------------------------------------

@dataclass
class SpeechResult:
    ok: bool
    engine: str = ""
    error: str = ""


def play_wav(path: Path, stream_holder: list) -> None:
    """Play a PCM WAV through sounddevice; ``stream_holder`` lets stop() abort it."""
    import sounddevice as sd

    with wave.open(str(path), "rb") as wav:
        sample_width = wav.getsampwidth()
        dtype = {1: "uint8", 2: "int16", 4: "int32"}.get(sample_width)
        if dtype is None:
            raise KokoroError(f"Unsupported WAV sample width: {sample_width}")
        with sd.RawOutputStream(
            samplerate=wav.getframerate(), channels=wav.getnchannels(), dtype=dtype, blocksize=2048
        ) as stream:
            stream_holder.append(stream)
            try:
                while True:
                    frames = wav.readframes(2048)
                    if not frames:
                        break
                    stream.write(frames)
            finally:
                if stream_holder:
                    stream_holder.clear()


class SpeechManager:
    """Queue of phrases -> natural voice, Kokoro, or the Windows voice (see the module notes)."""

    MAX_KOKORO_FAILURES = 2
    KOKORO_COOLDOWN_SECONDS = 300.0
    MAX_NATURAL_FAILURES = 2
    NATURAL_COOLDOWN_SECONDS = 120.0
    FIRST_PHRASE_CHARS = 90   # a short opening phrase gets the voice going sooner
    PREFETCH_PHRASES = 2      # natural-voice phrases fetched while the current one plays

    def __init__(
        self,
        settings=None,
        *,
        python_path: Path | None = None,
        helper_path: Path | None = None,
        fallback: WindowsSpeechFallback | None = None,
        player: Callable[[Path, list], None] | None = None,
        natural: NaturalVoice | None = None,
        pcm_player: Callable[..., None] | None = None,
        log_dir: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
        project_root: Path | None = None,
    ):
        if settings is None:
            from config.settings import NEXUSSettings

            settings = NEXUSSettings()
        self.settings = settings
        self.python_path = python_path if python_path is not None else find_kokoro_python(project_root)
        self.helper_path = helper_path if helper_path is not None else find_kokoro_helper()
        self.fallback = fallback if fallback is not None else WindowsSpeechFallback()
        self.natural = natural if natural is not None else NaturalVoice()
        self._player = player or play_wav
        self._pcm_player = pcm_player or play_pcm
        self._clock = clock
        if log_dir is None:
            from config.settings import USER_LOG_DIR

            log_dir = Path(USER_LOG_DIR)
        self._helper: KokoroHelper | None = None
        self._log_path = Path(log_dir) / "kokoro_worker.log"
        self._queue: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._generation = 0
        self._closed = False
        self._stream_holder: list = []
        self._failures = 0
        self._disabled_until = 0.0
        self._natural_failures = 0
        self._natural_disabled_until = 0.0
        self._prefetched: dict = {}   # (text, voice, speed) -> NaturalSpeechJob already fetching
        self._notices: list[str] = []
        self._last_engine = ""
        self._last_error = ""
        # Progress per tag (one tag per reply), so the interface can show words as they are spoken.
        self._words_done: dict = {}   # tag -> words in phrases already finished
        self._pending: dict = {}      # tag -> phrases queued or playing
        self._playing = None          # (tag, monotonic start, word start times, word count) of the current phrase
        self.speaking = False

    # ------------------------------------------------------------------ status
    @property
    def kokoro_installed(self) -> bool:
        return bool(self.python_path and self.helper_path)

    @property
    def kokoro_usable(self) -> bool:
        return self.kokoro_installed and self._clock() >= self._disabled_until

    @property
    def natural_installed(self) -> bool:
        return bool(self.natural.available)

    @property
    def natural_usable(self) -> bool:
        return self.natural_installed and self._clock() >= self._natural_disabled_until

    @property
    def available(self) -> bool:
        if self._closed:
            return False
        engine = self._engine_choice()
        if engine == "natural":
            return self.natural_installed
        if engine == "kokoro":
            return self.kokoro_installed
        if engine == "windows":
            return self.fallback.available
        return self.natural_installed or self.kokoro_installed or self.fallback.available

    @property
    def busy(self) -> bool:
        """True while anything is queued or being spoken."""
        return self._queue.unfinished_tasks > 0

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def last_engine(self) -> str:
        return self._last_engine

    def pop_notice(self) -> str:
        with self._lock:
            return self._notices.pop(0) if self._notices else ""

    def _notify(self, message: str) -> None:
        log.warning(message)
        with self._lock:
            if message not in self._notices:
                self._notices.append(message)

    def status(self) -> dict:
        return {
            "engine_setting": self._engine_choice(),
            "natural_installed": self.natural_installed,
            "natural_cooling_down": self.natural_installed and not self.natural_usable,
            "kokoro_installed": self.kokoro_installed,
            "kokoro_python": str(self.python_path) if self.python_path else "",
            "kokoro_cooling_down": self.kokoro_installed and not self.kokoro_usable,
            "fallback_available": self.fallback.available,
            "last_engine": self._last_engine,
            "last_error": self._last_error,
        }

    def _engine_choice(self) -> str:
        try:
            value = str(self.settings.tts_engine)
        except Exception:  # noqa: BLE001
            value = "auto"
        return value if value in {"auto", "natural", "kokoro", "windows"} else "auto"

    # ---------------------------------------------------------------- progress
    def spoken_words(self, tag) -> int:
        """How many words of the reply ``tag`` the voice has said so far (an estimate between word marks)."""
        with self._lock:
            done = self._words_done.get(tag, 0)
            playing = self._playing
        if playing is not None and playing[0] == tag:
            _tag, started, times, words = playing
            done += min(words, bisect.bisect_right(times, time.monotonic() - started))
        return done

    def is_speaking(self, tag) -> bool:
        """True while any phrase of the reply ``tag`` is queued or playing."""
        with self._lock:
            return self._pending.get(tag, 0) > 0

    def forget(self, tag) -> None:
        with self._lock:
            self._words_done.pop(tag, None)

    def _start_words(
        self, tag, text: str, starts=None, duration: float | None = None, speed: float = 1.0, live: bool = False
    ) -> None:
        """Mark the phrase as playing from now, with a start time for each of its words.

        ``live`` means ``starts`` is still being filled in by the engine as the audio arrives;
        it is used as is (the natural voice marks the same words NEXUS counts, one for one).
        """
        words = count_words(text)
        if live:
            times = starts
        elif words and starts:
            # Map the engine's word marks onto NEXUS's own word count (they rarely differ much).
            times = [starts[min(len(starts) - 1, i * len(starts) // words)] for i in range(words)]
        elif words and duration:
            times = [duration * i / words for i in range(words)]
        else:
            pace = _WORDS_PER_SECOND * max(0.5, speed)
            times = [i / pace for i in range(words)]
        with self._lock:
            self._playing = (tag, time.monotonic(), times, words)

    # ------------------------------------------------------------------- queue
    def _voice_and_speed(self, language: str) -> tuple[str, str, float]:
        lang, voice = LANGUAGE_VOICES.get(str(language or "auto").lower(), ("a", "af_heart"))
        if lang == "a":  # English: honour the user's chosen voice
            try:
                voice = str(self.settings.kokoro_voice)
            except Exception:  # noqa: BLE001
                pass
        try:
            speed = float(self.settings.kokoro_speed)
        except Exception:  # noqa: BLE001
            speed = 1.0
        return lang, voice, max(0.5, min(2.0, speed))

    def _natural_voice(self, language: str) -> str:
        code = str(language or "auto").lower()
        if code in NATURAL_LANGUAGE_VOICES:
            return NATURAL_LANGUAGE_VOICES[code]
        try:
            return str(self.settings.natural_voice)
        except Exception:  # noqa: BLE001
            return DEFAULT_NATURAL_VOICE

    def enqueue(self, text: str, language: str = "auto", tag=None) -> bool:
        """Queue text for speech. Returns False if nothing can speak it.

        ``tag`` names the reply the text belongs to, for :meth:`spoken_words`.
        """
        # Nothing playing means the listener is waiting: a short first phrase starts the voice sooner.
        # The natural voice streams its audio, so it starts just as fast with the whole phrase.
        starting = self._queue.unfinished_tasks == 0
        streams = self._engine_choice() in {"auto", "natural"} and self.natural_usable
        phrases = split_for_speech(text, first_max=self.FIRST_PHRASE_CHARS if starting and not streams else None)
        if not phrases:
            return True
        if not self.available:
            self._last_error = (
                "No speech engine is available. Connect to the internet for the natural voice, "
                "install Kokoro (see the Voice guide), or use Windows, which has a built-in voice."
            )
            return False
        lang, voice, speed = self._voice_and_speed(language)
        natural_voice = self._natural_voice(language)
        with self._lock:
            if self._closed:
                return False
            generation = self._generation
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="NEXUS-Speech", daemon=True)
                self._thread.start()
            for phrase in phrases:
                self._pending[tag] = self._pending.get(tag, 0) + 1
                self._queue.put((phrase, lang, voice, speed, generation, tag, natural_voice))
        return True

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            tag = None
            words = 0
            try:
                if item is None:
                    return
                text, lang, voice, speed, generation, tag, natural_voice = item
                words = count_words(text)
                with self._lock:
                    if self._closed:
                        return
                    stale = generation != self._generation
                if stale:
                    continue
                self.speaking = True
                self._speak_item(text, lang, voice, speed, generation, tag, natural_voice)
            except Exception:  # noqa: BLE001 - the speech thread must never die
                log.exception("speech item failed")
            finally:
                if item is not None:
                    with self._lock:
                        self._playing = None
                        # Count the phrase as said even if it failed, so the text keeps up.
                        self._words_done[tag] = self._words_done.get(tag, 0) + words
                        if tag in self._pending:
                            self._pending[tag] -= 1
                            if self._pending[tag] <= 0:
                                del self._pending[tag]
                self.speaking = self._queue.qsize() > 0
                self._queue.task_done()

    # ---------------------------------------------------------------- speaking
    def _current(self, generation: int) -> bool:
        with self._lock:
            return generation == self._generation and not self._closed

    def _speak_item(
        self, text: str, lang: str, voice: str, speed: float, generation: int, tag=None, natural_voice: str = ""
    ) -> SpeechResult:
        engine = self._engine_choice()
        natural_error = ""

        if engine in {"auto", "natural"}:
            if self.natural_usable:
                try:
                    self._speak_natural(text, natural_voice or self._natural_voice(lang), speed, generation, tag)
                    self._natural_failures = 0
                    self._last_error = ""
                    self._set_engine(self.natural.name)
                    return SpeechResult(True, self.natural.name)
                except Exception as error:  # noqa: BLE001
                    natural_error = str(error) or type(error).__name__
                    self._record_natural_failure(natural_error)
                    if engine == "natural":  # user chose this voice only: do not switch voices
                        self._last_error = natural_error
                        self._notify(f"The natural voice is not working: {natural_error}")
                        return SpeechResult(False, self.natural.name, natural_error)
            elif engine == "natural":
                reason = ("The natural voice is not installed (the edge-tts package is missing)."
                          if not self.natural_installed else "The natural voice is paused after repeated errors.")
                self._last_error = reason
                self._notify(f"Speech is set to the natural voice only. {reason}")
                return SpeechResult(False, self.natural.name, reason)
            if not self._current(generation):
                return SpeechResult(True, "cancelled")

        want_kokoro = engine in {"auto", "kokoro"} and self.kokoro_usable
        kokoro_error = ""

        if want_kokoro:
            try:
                self._speak_kokoro(text, lang, voice, speed, generation, tag)
                self._failures = 0
                self._last_error = ""
                if natural_error and self._last_engine != "Kokoro":
                    self._notify(f"Natural voice unavailable ({natural_error}). Using Kokoro instead.")
                self._set_engine("Kokoro")
                return SpeechResult(True, "Kokoro")
            except Exception as error:  # noqa: BLE001
                kokoro_error = str(error) or type(error).__name__
                self._record_kokoro_failure(kokoro_error)
                if engine == "kokoro":  # user insisted on Kokoro: do not switch voices
                    self._last_error = kokoro_error
                    return SpeechResult(False, "Kokoro", kokoro_error)
        elif engine == "kokoro":
            reason = "Kokoro is not installed yet." if not self.kokoro_installed else "Kokoro is paused after repeated errors."
            self._last_error = reason
            self._notify(f"Speech is set to Kokoro only, but {reason[0].lower() + reason[1:]}")
            return SpeechResult(False, "Kokoro", reason)

        if not self._current(generation):
            return SpeechResult(True, "cancelled")
        if self.fallback.available:
            try:
                if engine == "auto":
                    why = kokoro_error or ("Kokoro is not installed" if not self.kokoro_installed else "Kokoro is paused after errors")
                    self._announce_fallback(why, natural_error)
                self._start_words(tag, text, speed=speed)
                self.fallback.speak(text, speed)
                self._set_engine(self.fallback.name)
                return SpeechResult(True, self.fallback.name)
            except Exception as error:  # noqa: BLE001
                self._last_error = str(error)
                self._notify(f"Speech failed: {error}")
                return SpeechResult(False, self.fallback.name, str(error))
        self._last_error = kokoro_error or "No speech engine is available."
        return SpeechResult(False, "", self._last_error)

    def _natural_job(self, text: str, voice: str, speed: float) -> NaturalSpeechJob:
        """The fetch for this phrase: started ahead of time if possible, otherwise now."""
        with self._lock:
            job = self._prefetched.pop((text, voice, speed), None)
        return job if job is not None else NaturalSpeechJob(self.natural, text, voice, speed)

    def _prefetch_next(self, generation: int) -> None:
        """Start fetching the next queued phrases so they play straight after this one."""
        with self._queue.mutex:
            upcoming = [item for item in list(self._queue.queue)[: self.PREFETCH_PHRASES] if item is not None]
        for text, _lang, _voice, speed, item_generation, _tag, natural_voice in upcoming:
            key = (text, natural_voice, speed)
            with self._lock:
                if item_generation == generation and key not in self._prefetched:
                    self._prefetched[key] = NaturalSpeechJob(self.natural, *key)

    def _speak_natural(self, text: str, voice: str, speed: float, generation: int, tag=None) -> None:
        job = self._natural_job(text, voice, speed)
        first = job.next_chunk(NaturalVoice.TIMEOUT_SECONDS + 5)
        if first is None:  # nothing came back: let the next engine take over
            raise job.error or SpeechError("the natural voice service returned no audio")
        if not self._current(generation):
            return
        self._prefetch_next(generation)

        def chunks():
            yield first
            while self._current(generation):
                chunk = job.next_chunk(15.0)
                if chunk is None:
                    if job.error is not None:  # cut off part-way: what was heard stays, the rest is skipped
                        log.warning("natural voice stopped part-way: %s", job.error)
                    return
                yield chunk

        self._start_words(tag, text, starts=job.word_starts, live=True)
        try:
            self._pcm_player(chunks(), job.rate, self._stream_holder)
        except Exception:  # noqa: BLE001
            if self._current(generation):
                raise
            # stop() aborted the audio stream; that is not a failure

    def _record_natural_failure(self, error: str) -> None:
        self._natural_failures += 1
        log.error("natural voice failed (%s): %s", self._natural_failures, error)
        if self._natural_failures >= self.MAX_NATURAL_FAILURES:
            self._natural_disabled_until = self._clock() + self.NATURAL_COOLDOWN_SECONDS
            self._natural_failures = 0

    def _speak_kokoro(self, text: str, lang: str, voice: str, speed: float, generation: int, tag=None) -> None:
        if self._helper is None:
            self._helper = KokoroHelper(self.python_path, self.helper_path, self._log_path)  # type: ignore[arg-type]
        reply = self._helper.request({"text": text, "lang": lang, "voice": voice, "speed": speed})
        path = reply.get("path") or ""
        if not path:
            return
        wav_path = Path(path)
        try:
            if self._current(generation):
                duration = None
                try:
                    with wave.open(str(wav_path), "rb") as wav:
                        duration = wav.getnframes() / max(1, wav.getframerate())
                except (OSError, wave.Error, EOFError):
                    pass
                self._start_words(tag, text, duration=duration, speed=speed)
                self._player(wav_path, self._stream_holder)
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _record_kokoro_failure(self, error: str) -> None:
        self._failures += 1
        self._last_error = error
        log.error("Kokoro failed (%s): %s", self._failures, error)
        if self._helper is not None:
            self._helper.stop()
        if self._failures >= self.MAX_KOKORO_FAILURES:
            self._disabled_until = self._clock() + self.KOKORO_COOLDOWN_SECONDS
            self._failures = 0

    def _announce_fallback(self, reason: str, natural_error: str = "") -> None:
        if self._last_engine != self.fallback.name:
            if natural_error:
                reason = f"natural voice: {natural_error}; Kokoro: {reason[0].lower() + reason[1:]}"
                self._notify(f"Natural and Kokoro voices unavailable ({reason}). Using the {self.fallback.name} instead.")
            else:
                self._notify(f"Kokoro voice unavailable ({reason}). Using the {self.fallback.name} instead.")

    def _set_engine(self, name: str) -> None:
        if name != self._last_engine:
            log.info("speech engine: %s", name)
        self._last_engine = name

    # -------------------------------------------------------------- synchronous
    def test(self, text: str = "Hello, I am NEXUS. This is how I sound.", language: str = "en") -> SpeechResult:
        """Speak one phrase right now on the calling thread (for setup tests)."""
        lang, voice, speed = self._voice_and_speed(language)
        with self._lock:
            generation = self._generation
        try:
            return self._speak_item(clean_for_speech(text), lang, voice, speed, generation, None, self._natural_voice(language))
        finally:
            with self._lock:
                self._playing = None

    # ------------------------------------------------------------------ control
    def stop(self) -> None:
        """Cancel current playback and drop everything queued."""
        with self._lock:
            self._generation += 1
            holder = list(self._stream_holder)
            self._pending.clear()
            self._prefetched.clear()
            self._playing = None
        for stream in holder:
            try:
                stream.abort()
            except Exception:  # noqa: BLE001
                pass
        self.fallback.stop()
        saw_sentinel = False
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            saw_sentinel = saw_sentinel or item is None
            self._queue.task_done()
        if saw_sentinel:
            self._queue.put(None)  # keep the shutdown request
        self.speaking = False

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self.stop()
        self._queue.put(None)
        if self._helper is not None:
            self._helper.stop()
            self._helper = None
