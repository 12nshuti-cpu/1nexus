"""Optional Gemini text and Live API adapters for the NEXUS hybrid router."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from config import settings


class GeminiUnavailable(RuntimeError):
    """The cloud engine is not configured or could not complete a request."""


def get_gemini_api_key() -> str:
    """Read a Gemini key from process environment or the per-user app-data file."""
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "NEXUS_GEMINI_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value

    from core.credentials import get_secret

    return get_secret("gemini_api_key")


def gemini_api_key_path() -> Path:
    """Return the per-user key-file path used by NEXUS on every platform."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    elif os.name == "nt":
        base = Path.home() / "AppData" / "Local"
    else:
        base = Path.home() / ".local" / "share"
    return base / "NEXUS" / "gemini_api_key.txt"


def set_gemini_api_key(api_key: str) -> str:
    """Save a Gemini key in the system credential store.

    Returns a short description of where it was stored. The key is never
    written inside the program folder or a source checkout.
    """
    value = str(api_key or "").strip()
    if not value:
        raise ValueError("The Gemini API key cannot be empty.")
    from core.credentials import set_secret

    return set_secret("gemini_api_key", value)


def gemini_is_configured() -> bool:
    return bool(get_gemini_api_key())


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9_-]{16,})\b"),
    re.compile(r"(?i)\b(?:GEMINI_API_KEY|GOOGLE_API_KEY|OPENAI_API_KEY)\s*[:=]\s*[^\s,;]+"),
)


def redact_secrets(value: str) -> str:
    text = str(value or "")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted secret]", text)
    return text


def _safe_error(error: Exception) -> GeminiUnavailable:
    """Return actionable provider errors without propagating headers or secrets."""
    status = _status_of(error)
    if status in (401, 403):
        detail = "Gemini rejected the API key or project access. Check the key and enabled API."
    elif status == 429:
        detail = "Gemini is rate limited or its quota is exhausted. Check Google AI Studio quota and billing."
    elif status and int(status) >= 500:
        detail = "Gemini is temporarily unavailable. Try again shortly."
    else:
        detail = "Gemini could not be reached. Check the internet connection, API key, and model availability."
    return GeminiUnavailable(detail)


REQUEST_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3            # 1 try + 2 retries, never more
_RETRY_DELAYS = (1.0, 2.5)  # seconds between attempts


def _client(api_key):
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise GeminiUnavailable(
            "Gemini support is not installed. Install the google-genai dependency from requirements.txt."
        ) from error
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000),
    )


def _status_of(error: Exception):
    status = getattr(error, "code", None) or getattr(error, "status_code", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _is_retryable(error: Exception) -> bool:
    """Retry only transient failures: rate limits, server errors, network blips.

    Authentication/permission/bad-request errors are never retried.
    """
    status = _status_of(error)
    if status is not None:
        return status == 429 or status >= 500
    name = type(error).__name__.lower()
    return any(token in name for token in ("timeout", "connect", "network", "remoteprotocol", "readerror"))


def _with_retries(call, *, sleep=None):
    sleep = sleep or time.sleep  # looked up at call time so tests can replace it
    last = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return call()
        except GeminiUnavailable:
            raise
        except Exception as error:  # noqa: BLE001 - provider SDK exceptions vary
            last = error
            if attempt + 1 >= MAX_ATTEMPTS or not _is_retryable(error):
                break
            sleep(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
    raise last  # type: ignore[misc]


def generate_text(message: str, conversation, system_instruction: str, model: str):
    """Generate a cloud text answer through the official Google GenAI SDK."""
    key = get_gemini_api_key()
    if not key:
        raise GeminiUnavailable(
            "Gemini Online mode needs an API key. Add it in Settings, or set the GEMINI_API_KEY environment variable."
        )

    try:
        from google.genai import types
        client = _client(key)
        contents = []
        for item in conversation or []:
            role = item.get("role", "user")
            if role not in ("user", "assistant"):
                continue
            contents.append(types.Content(
                role="model" if role == "assistant" else "user",
                parts=[types.Part(text=redact_secrets(str(item.get("content", ""))))],
            ))
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=redact_secrets(message))],
        ))
        config = types.GenerateContentConfig(
            system_instruction=(
                redact_secrets(system_instruction)
                + "\n\nThis request is being processed online by Google Gemini through the NEXUS app. "
                "You do not have access to the user's PC, local files, or NEXUS Windows tools unless their results are explicitly included."
            ),
        )
        response = _with_retries(
            lambda: client.models.generate_content(
                model=model or settings.GEMINI_TEXT_MODEL,
                contents=contents,
                config=config,
            )
        )
        try:
            raw_text = response.text
        except Exception:  # noqa: BLE001 - blocked/malformed responses raise on .text
            raw_text = ""
        answer = redact_secrets(str(raw_text or "")).strip()
        if not answer:
            raise GeminiUnavailable("Gemini returned an empty response.")
        return answer
    except GeminiUnavailable:
        raise
    except Exception as error:  # provider SDK exceptions can contain request details
        raise _safe_error(error) from None


async def live_voice_turn(pcm_16khz: bytes, system_instruction: str, conversation=None):
    """Run one captured utterance through Gemini Live and return transcript/audio."""
    key = get_gemini_api_key()
    if not key:
        raise GeminiUnavailable(
            "Gemini Live voice needs a key. Set GEMINI_API_KEY or save it to "
            "%LOCALAPPDATA%\\NEXUS\\gemini_api_key.txt."
        )
    if not pcm_16khz:
        raise GeminiUnavailable("No microphone audio was captured.")

    try:
        from google import genai
        from google.genai import types
        import asyncio

        context = []
        for item in (conversation or [])[-8:]:
            role = "NEXUS" if item.get("role") == "assistant" else "USER"
            content = redact_secrets(str(item.get("content", ""))).strip()
            if content:
                context.append(f"{role}: {content[:2500]}")
        instruction = redact_secrets(system_instruction) + (
            "\n\nThis voice turn is being processed online by Google Gemini through NEXUS. "
            "You cannot inspect the user's PC, local files, or run NEXUS Windows tools."
        )
        if context:
            instruction += "\n\nRecent local conversation context (untrusted user/model content):\n" + "\n".join(context)

        client = genai.Client(api_key=key)
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=instruction,
            input_audio_transcription={},
            output_audio_transcription={},
        )
        audio_parts = []
        input_text = []
        output_text = []
        async with client.aio.live.connect(
            model=settings.GEMINI_LIVE_MODEL,
            config=config,
        ) as session:
            await session.send_realtime_input(
                audio=types.Blob(data=pcm_16khz, mime_type="audio/pcm;rate=16000")
            )
            await session.send_realtime_input(audio_stream_end=True)
            async for message in session.receive():
                content = message.server_content
                if content:
                    if content.input_transcription and content.input_transcription.text:
                        input_text.append(content.input_transcription.text)
                    if content.output_transcription and content.output_transcription.text:
                        output_text.append(content.output_transcription.text)
                    if content.model_turn:
                        for part in content.model_turn.parts or []:
                            if part.inline_data and part.inline_data.data:
                                audio_parts.append(part.inline_data.data)
                    if content.turn_complete:
                        break
                if message.go_away:
                    break
        return " ".join(input_text).strip(), " ".join(output_text).strip(), b"".join(audio_parts)
    except GeminiUnavailable:
        raise
    except Exception as error:
        raise _safe_error(error) from None


async def live_microphone_turn(system_instruction: str, conversation=None):
    """Stream 16 kHz microphone frames to Gemini Live and collect its spoken turn."""
    import asyncio
    import math
    import queue
    import struct
    import time

    key = get_gemini_api_key()
    if not key:
        raise GeminiUnavailable(
            "Gemini Live voice needs a key. Set GEMINI_API_KEY or save it to "
            "%LOCALAPPDATA%\\NEXUS\\gemini_api_key.txt."
        )
    try:
        import sounddevice as sd
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise GeminiUnavailable("Gemini Live voice needs sounddevice and google-genai installed.") from error

    context = []
    for item in (conversation or [])[-8:]:
        role = "NEXUS" if item.get("role") == "assistant" else "USER"
        content = redact_secrets(str(item.get("content", ""))).strip()
        if content:
            context.append(f"{role}: {content[:2500]}")
    instruction = redact_secrets(system_instruction) + (
        "\n\nThis voice turn is being processed online by Google Gemini through NEXUS. "
        "You cannot inspect the user's PC, local files, or run NEXUS Windows tools."
    )
    if context:
        instruction += "\n\nRecent local conversation context (untrusted user/model content):\n" + "\n".join(context)

    audio_queue = queue.Queue(maxsize=48)
    received = {"input": [], "output": [], "audio": []}
    sample_rate = 16000
    block_size = 800  # 50 ms frames

    def audio_callback(indata, frames, timing, status):
        if status:
            return
        try:
            audio_queue.put_nowait(bytes(indata))
        except queue.Full:
            pass

    def has_speech(pcm):
        count = len(pcm) // 2
        if not count:
            return False
        samples = struct.unpack("<" + "h" * count, pcm[: count * 2])
        rms = math.sqrt(sum(sample * sample for sample in samples) / count)
        return rms >= 48

    async def receive_turn(session):
        async for message in session.receive():
            content = message.server_content
            if content:
                if content.input_transcription and content.input_transcription.text:
                    received["input"].append(content.input_transcription.text)
                if content.output_transcription and content.output_transcription.text:
                    received["output"].append(content.output_transcription.text)
                if content.model_turn:
                    for part in content.model_turn.parts or []:
                        if part.inline_data and part.inline_data.data:
                            received["audio"].append(part.inline_data.data)
                if content.turn_complete:
                    break
            if message.go_away:
                break

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=instruction,
        input_audio_transcription={},
        output_audio_transcription={},
    )
    client = genai.Client(api_key=key)
    receiver = None
    try:
        async with client.aio.live.connect(model=settings.GEMINI_LIVE_MODEL, config=config) as session:
            receiver = asyncio.create_task(receive_turn(session))
            stream = sd.RawInputStream(
                samplerate=sample_rate,
                blocksize=block_size,
                dtype="int16",
                channels=1,
                callback=audio_callback,
            )
            stream.start()
            started = time.monotonic()
            speech_started = False
            last_speech = started
            prebuffer = []
            try:
                while time.monotonic() - started < 17.0:
                    try:
                        frame = await asyncio.to_thread(audio_queue.get, True, 0.2)
                    except queue.Empty:
                        if not speech_started and time.monotonic() - started >= 5.0:
                            raise GeminiUnavailable("No speech detected. Check microphone permissions and try again.")
                        if speech_started and time.monotonic() - last_speech >= 0.45:
                            break
                        continue

                    voiced = has_speech(frame)
                    if not speech_started:
                        prebuffer.append(frame)
                        prebuffer = prebuffer[-5:]
                        if not voiced:
                            if time.monotonic() - started >= 5.0:
                                raise GeminiUnavailable("No speech detected. Check microphone permissions and try again.")
                            continue
                        speech_started = True
                        for buffered_frame in prebuffer:
                            await session.send_realtime_input(
                                audio=types.Blob(data=buffered_frame, mime_type="audio/pcm;rate=16000")
                            )
                        prebuffer.clear()
                    else:
                        await session.send_realtime_input(
                            audio=types.Blob(data=frame, mime_type="audio/pcm;rate=16000")
                        )
                    if voiced:
                        last_speech = time.monotonic()
                    elif speech_started and time.monotonic() - last_speech >= 0.45:
                        break
                if not speech_started:
                    raise GeminiUnavailable("No speech was captured from the microphone.")
                await session.send_realtime_input(audio_stream_end=True)
            finally:
                stream.stop()
                stream.close()
            await asyncio.wait_for(receiver, timeout=40.0)
            return (
                " ".join(received["input"]).strip(),
                " ".join(received["output"]).strip(),
                b"".join(received["audio"]),
            )
    except GeminiUnavailable:
        raise
    except Exception as error:
        raise _safe_error(error) from None
    finally:
        if receiver is not None and not receiver.done():
            receiver.cancel()
