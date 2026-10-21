"""Speech output for NEXUS: Kokoro (neural, local) with a Windows-voice fallback.

Why a separate process
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
* If Kokoro is missing or keeps failing, the Windows system voice is used and
  the user is *told* (:meth:`SpeechManager.pop_notice`); it never switches
  silently. After repeated Kokoro failures it is not retried for a while.
* Error text is never spoken as if it were an answer.
"""
from __future__ import annotations

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


def split_for_speech(text: str, max_chars: int = 240) -> list[str]:
    """Split into phrase-sized chunks so playback starts quickly."""
    value = clean_for_speech(text)
    if not value:
        return []
    sentences = re.split(r"(?<=[.!?…])\s+", value)
    chunks: list[str] = []
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

class KokoroError(RuntimeError):
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
            status = json.loads(self._next_line(self.startup_timeout))
        except json.JSONDecodeError as error:
            self.stop()
            raise KokoroError("The Kokoro helper returned an invalid startup message.") from error
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
            reply = json.loads(self._next_line(self.request_timeout))
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
    """Queue of phrases -> Kokoro (preferred) or the Windows voice (fallback)."""

    MAX_KOKORO_FAILURES = 2
    KOKORO_COOLDOWN_SECONDS = 300.0

    def __init__(
        self,
        settings=None,
        *,
        python_path: Path | None = None,
        helper_path: Path | None = None,
        fallback: WindowsSpeechFallback | None = None,
        player: Callable[[Path, list], None] | None = None,
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
        self._player = player or play_wav
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
        self._notices: list[str] = []
        self._last_engine = ""
        self._last_error = ""
        self.speaking = False

    # ------------------------------------------------------------------ status
    @property
    def kokoro_installed(self) -> bool:
        return bool(self.python_path and self.helper_path)

    @property
    def kokoro_usable(self) -> bool:
        return self.kokoro_installed and self._clock() >= self._disabled_until

    @property
    def available(self) -> bool:
        if self._closed:
            return False
        engine = self._engine_choice()
        if engine == "kokoro":
            return self.kokoro_installed
        if engine == "windows":
            return self.fallback.available
        return self.kokoro_installed or self.fallback.available

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
        return value if value in {"auto", "kokoro", "windows"} else "auto"

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

    def enqueue(self, text: str, language: str = "auto") -> bool:
        """Queue text for speech. Returns False if nothing can speak it."""
        phrases = split_for_speech(text)
        if not phrases:
            return True
        if not self.available:
            self._last_error = (
                "No speech engine is available. Install Kokoro (see the Voice guide) "
                "or use Windows, which has a built-in voice."
            )
            return False
        lang, voice, speed = self._voice_and_speed(language)
        with self._lock:
            if self._closed:
                return False
            generation = self._generation
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="NEXUS-Speech", daemon=True)
                self._thread.start()
            for phrase in phrases:
                self._queue.put((phrase, lang, voice, speed, generation))
        return True

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                text, lang, voice, speed, generation = item
                with self._lock:
                    if self._closed:
                        return
                    stale = generation != self._generation
                if stale:
                    continue
                self.speaking = True
                self._speak_item(text, lang, voice, speed, generation)
            except Exception:  # noqa: BLE001 - the speech thread must never die
                log.exception("speech item failed")
            finally:
                self.speaking = self._queue.qsize() > 0
                self._queue.task_done()

    # ---------------------------------------------------------------- speaking
    def _current(self, generation: int) -> bool:
        with self._lock:
            return generation == self._generation and not self._closed

    def _speak_item(self, text: str, lang: str, voice: str, speed: float, generation: int) -> SpeechResult:
        engine = self._engine_choice()
        want_kokoro = engine in {"auto", "kokoro"} and self.kokoro_usable
        kokoro_error = ""

        if want_kokoro:
            try:
                self._speak_kokoro(text, lang, voice, speed, generation)
                self._failures = 0
                self._last_error = ""
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
                    self._announce_fallback(why)
                self.fallback.speak(text, speed)
                self._set_engine(self.fallback.name)
                return SpeechResult(True, self.fallback.name)
            except Exception as error:  # noqa: BLE001
                self._last_error = str(error)
                self._notify(f"Speech failed: {error}")
                return SpeechResult(False, self.fallback.name, str(error))
        self._last_error = kokoro_error or "No speech engine is available."
        return SpeechResult(False, "", self._last_error)

    def _speak_kokoro(self, text: str, lang: str, voice: str, speed: float, generation: int) -> None:
        if self._helper is None:
            self._helper = KokoroHelper(self.python_path, self.helper_path, self._log_path)  # type: ignore[arg-type]
        reply = self._helper.request({"text": text, "lang": lang, "voice": voice, "speed": speed})
        path = reply.get("path") or ""
        if not path:
            return
        wav_path = Path(path)
        try:
            if self._current(generation):
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

    def _announce_fallback(self, reason: str) -> None:
        if self._last_engine != self.fallback.name:
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
        return self._speak_item(clean_for_speech(text), lang, voice, speed, generation)

    # ------------------------------------------------------------------ control
    def stop(self) -> None:
        """Cancel current playback and drop everything queued."""
        with self._lock:
            self._generation += 1
            holder = list(self._stream_holder)
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
