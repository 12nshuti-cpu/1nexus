"""Fast online voice I/O for NEXUS.



STT uses OpenAI's realtime transcription path first, so microphone audio is

streamed while the user is speaking instead of waiting for a complete WAV

upload. A bounded HTTP gpt-transcribe fallback is kept for compatibility.



TTS uses gpt-4o-mini-tts with PCM streaming so playback can begin before the

whole response has downloaded.



Wake-word detection is deliberately *not* handled here. NEXUS uses the local

wake detector before this service is invoked in background mode.

"""



from __future__ import annotations



import json

import math

import os

import queue
import subprocess
import sys
import wave

import re

import statistics

import threading

import time

from array import array

from pathlib import Path

from typing import Optional



import requests

try:
    import sounddevice as sd
except (ImportError, OSError) as _audio_import_error:  # PortAudio missing/unusable
    from core.audio_compat import MissingSoundDevice

    sd = MissingSoundDevice(_audio_import_error)

try:

    import websocket

except ModuleNotFoundError:  # pragma: no cover - depends on installed voice extras

    websocket = None





# The Kokoro/Windows-voice speech queue now lives in core.speech. The old name
# is kept so existing imports keep working.
from core.speech import SpeechManager as KokoroSpeechQueue  # noqa: E402,F401
from core.speech import clean_for_speech as _clean_for_speech_text  # noqa: E402


class RealtimeUnavailable(RuntimeError):

    """Raised when the realtime STT transport itself is unavailable."""





class VoiceService:

    """Responsive online STT/TTS service for NEXUS."""



    LANGUAGE_LABELS = {

        "auto": "Automatic",

        "en": "English",

        "fr": "French",

        "rw": "Kinyarwanda",

        "sw": "Swahili",

        "es": "Spanish",

        "de": "German",

        "it": "Italian",

        "pt": "Portuguese",

    }



    REALTIME_STT_MODEL = "gpt-live-transcribe"

    HTTP_STT_MODEL = "gpt-transcribe"

    TTS_MODEL = "gpt-4o-mini-tts"

    TTS_VOICE = "marin"



    API_BASE = "https://api.openai.com/v1"

    STT_URL = f"{API_BASE}/audio/transcriptions"

    TTS_URL = f"{API_BASE}/audio/speech"

    REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-live-transcribe"



    API_KEY_FILE_NAMES = (

        "openai_api_key.txt",

        "OPENAI_API_KEY.txt",

    )



    STT_KEYWORDS = (

        "NEXUS",

        "open NEXUS",

        "open up NEXUS",

        "VS Code",

        "Chrome",

        "Google Chrome",

        "Microsoft Edge",

        "Notepad",

        "File Explorer",

        "Ollama",

        "llama3.1:8b",

    )



    _tts_lock = threading.RLock()

    _api_session = None

    _api_session_lock = threading.Lock()
    _active_kokoro_queue = None



    def __init__(self):

        self.sample_rate = 24000

        self.audio_queue: queue.Queue[bytes] = queue.Queue()

        self._last_stream_error = ""



    # ============================================================

    # API KEY / HTTP

    # ============================================================



    @classmethod

    def _candidate_key_files(cls):

        paths = []

        local_app_data = os.environ.get("LOCALAPPDATA")

        app_data = os.environ.get("APPDATA")



        for base in (local_app_data, app_data):

            if not base:

                continue

            nexus_dir = Path(base) / "NEXUS"

            for filename in cls.API_KEY_FILE_NAMES:

                paths.append(nexus_dir / filename)



        # The project/program folder is deliberately NOT searched: a key file
        # there is one `git add .` away from being published or installed.
        return paths



    @classmethod

    def get_api_key(cls) -> str:

        for variable in ("OPENAI_API_KEY", "NEXUS_OPENAI_API_KEY"):

            value = os.environ.get(variable, "").strip()

            if value:

                return value



        from core.credentials import get_secret

        return get_secret("openai_api_key", cls._candidate_key_files())



    @classmethod

    def set_api_key(cls, api_key: str) -> str:

        api_key = str(api_key or "").strip()

        if not api_key:

            raise ValueError("The OpenAI API key is empty.")



        from core.credentials import set_secret

        return set_secret("openai_api_key", api_key)



    @classmethod

    def has_api_key(cls) -> bool:

        return bool(cls.get_api_key())



    @classmethod

    def _session(cls):

        with cls._api_session_lock:

            if cls._api_session is None:

                session = requests.Session()

                session.headers.update({"User-Agent": "NEXUS-Voice/0.5.0"})

                cls._api_session = session

            return cls._api_session



    @classmethod

    def _headers(cls):

        key = cls.get_api_key()

        if not key:

            raise RuntimeError(

                "Online NEXUS voice needs an OpenAI API key. "

                "Set OPENAI_API_KEY or place it in %LOCALAPPDATA%\\NEXUS\\openai_api_key.txt."

            )

        return {"Authorization": f"Bearer {key}"}



    # ============================================================

    # MICROPHONE CAPTURE / LOCAL VAD

    # ============================================================



    @staticmethod

    def _rms_level(data: bytes) -> float:

        try:

            samples = array("h")

            samples.frombytes(data)

            if not samples:

                return 0.0

            total = sum(sample * sample for sample in samples)

            return math.sqrt(total / len(samples))

        except Exception:

            return 0.0



    def _audio_callback(self, indata, frames, callback_time, status):

        self.audio_queue.put(bytes(indata))



    def _clear_audio_queue(self):

        while True:

            try:

                self.audio_queue.get_nowait()

            except queue.Empty:

                return



    def _capture_wav(

        self,

        *,

        wait_timeout: float,

        maximum_recording_time: float,

        end_silence: float,

        cancel_event: Optional[threading.Event] = None,

    ) -> bytes:

        """Fast local speech capture used by the wake detector."""

        import io

        import wave



        self._clear_audio_queue()

        capture_rate = 16000

        blocksize = 800  # 50 ms

        block_duration = blocksize / capture_rate

        calibration_window = 0.18

        captured_chunks: list[bytes] = []

        pre_speech_chunks: list[bytes] = []

        noise_samples: list[float] = []

        speech_started = False

        last_speech_at = None

        started = time.monotonic()



        try:

            with sd.RawInputStream(

                samplerate=capture_rate,

                blocksize=blocksize,

                dtype="int16",

                channels=1,

                callback=self._audio_callback,

            ):

                while True:

                    if cancel_event is not None and cancel_event.is_set():

                        raise RuntimeError("Voice capture cancelled.")



                    elapsed = time.monotonic() - started

                    if not speech_started and elapsed >= wait_timeout:

                        raise RuntimeError(

                            "No speech detected. Check microphone permissions and speak after activating NEXUS."

                        )

                    if speech_started and elapsed >= maximum_recording_time:

                        break



                    try:

                        data = self.audio_queue.get(timeout=0.08)

                    except queue.Empty:

                        continue



                    level = self._rms_level(data)

                    if not speech_started:

                        pre_speech_chunks.append(data)

                        max_pre = max(3, int(0.28 / block_duration))

                        if len(pre_speech_chunks) > max_pre:

                            pre_speech_chunks.pop(0)



                        if elapsed <= calibration_window:

                            noise_samples.append(level)



                        noise_floor = statistics.median(noise_samples) if noise_samples else 30.0

                        threshold = max(48.0, noise_floor * 1.65)



                        if elapsed >= 0.16 and level >= threshold:

                            speech_started = True

                            last_speech_at = time.monotonic()

                            captured_chunks.extend(pre_speech_chunks)

                            pre_speech_chunks.clear()

                            captured_chunks.append(data)

                        continue



                    captured_chunks.append(data)

                    speaking_threshold = max(

                        42.0,

                        (statistics.median(noise_samples) if noise_samples else 24.0) * 1.40,

                    )

                    if level >= speaking_threshold:

                        last_speech_at = time.monotonic()

                    elif last_speech_at is not None and time.monotonic() - last_speech_at >= end_silence:

                        break



        except sd.PortAudioError as error:

            raise RuntimeError(

                "The microphone could not be accessed. Check Windows microphone permissions and the selected input device.\n\n"

                f"Audio error: {error}"

            ) from error

        except RuntimeError:

            raise

        except Exception as error:

            raise RuntimeError(f"Voice capture failed: {error}") from error



        if not captured_chunks:

            raise RuntimeError("No speech was captured from the microphone.")



        buffer = io.BytesIO()

        with wave.open(buffer, "wb") as wav_file:

            wav_file.setnchannels(1)

            wav_file.setsampwidth(2)

            wav_file.setframerate(capture_rate)

            wav_file.writeframes(b"".join(captured_chunks))

        return buffer.getvalue()



    def capture_local_speech(

        self,

        *,

        wait_timeout=1.0,

        maximum_recording_time=3.0,

        end_silence=0.35,

        cancel_event: Optional[threading.Event] = None,

    ) -> bytes:

        return self._capture_wav(

            wait_timeout=float(wait_timeout),

            maximum_recording_time=float(maximum_recording_time),

            end_silence=float(end_silence),

            cancel_event=cancel_event,

        )



    # ============================================================

    # REALTIME STT

    # ============================================================



    @classmethod

    def _language_code(cls, language):

        language = str(language or "auto").strip().lower()

        if language not in cls.LANGUAGE_LABELS or language == "auto":

            return None

        return language



    @classmethod

    def _realtime_session_message(cls, language):

        transcription = {

            "model": cls.REALTIME_STT_MODEL,

            "prompt": (

                "Speech is addressed to a Windows desktop assistant named NEXUS. "

                "Preserve application names, commands, file paths, URLs, numbers and technical terms."

            ),

            "keywords": list(cls.STT_KEYWORDS),

            "delay": "minimal",

        }

        language_code = cls._language_code(language)

        if language_code:

            transcription["languages"] = [language_code]



        return {

            "type": "session.update",

            "session": {

                "type": "transcription",

                "audio": {

                    "input": {

                        "format": {"type": "audio/pcm", "rate": 24000},

                        "transcription": transcription,

                        "turn_detection": None,

                    }

                },

            },

        }



    def _listen_realtime(

        self,

        language="auto",

        *,

        wait_timeout=3.0,

        maximum_recording_time=12.0,

        end_silence=0.38,

        cancel_event: Optional[threading.Event] = None,

    ):

        """Stream live microphone audio into GPT Live Transcribe."""

        api_key = self.get_api_key()

        if not api_key:

            raise RuntimeError(

                "Online NEXUS voice needs an OpenAI API key."

            )



        if websocket is None:

            raise RuntimeError(

                "The websocket-client package is missing. Run `python -m pip install websocket-client`."

            )



        try:

            ws = websocket.create_connection(

                self.REALTIME_URL,

                header=[

                    f"Authorization: Bearer {api_key}",

                ],

                timeout=8,

                enable_multithread=True,

            )

        except Exception as error:

            raise RealtimeUnavailable(f"Realtime STT connection failed: {error}") from error



        stop_receiver = threading.Event()

        session_ready = threading.Event()

        transcript_done = threading.Event()

        receiver_error: list[str] = []

        transcript_parts: list[str] = []

        final_transcript: list[str] = []



        try:

            ws.settimeout(0.50)



            def receive_events():

                while not stop_receiver.is_set():

                    try:

                        message = ws.recv()

                    except websocket.WebSocketTimeoutException:

                        continue

                    except Exception as error:

                        if not stop_receiver.is_set():

                            receiver_error.append(str(error))

                            transcript_done.set()

                        return



                    if not message:

                        continue



                    try:

                        event = json.loads(message)

                    except (TypeError, ValueError):

                        continue



                    event_type = event.get("type", "")

                    if event_type in {"session.created", "session.updated"}:

                        if event_type == "session.updated":

                            session_ready.set()

                    elif event_type in {

                        "conversation.item.input_audio_transcription.delta",

                        "transcript.text.delta",

                    }:

                        delta = str(event.get("delta", ""))

                        if delta:

                            transcript_parts.append(delta)

                    elif event_type in {

                        "conversation.item.input_audio_transcription.completed",

                        "transcript.text.done",

                    }:

                        text = str(event.get("transcript", "") or event.get("text", "")).strip()

                        if text:

                            final_transcript.append(text)

                        transcript_done.set()

                    elif event_type == "error":

                        error_obj = event.get("error", {})

                        message_text = str(error_obj.get("message", "Realtime transcription failed."))

                        receiver_error.append(message_text)

                        transcript_done.set()



            receiver = threading.Thread(

                target=receive_events,

                name="NEXUS-Realtime-STT-Receiver",

                daemon=True,

            )

            receiver.start()



            ws.send(json.dumps(self._realtime_session_message(language)))

            if not session_ready.wait(timeout=4.0):

                if receiver_error:

                    raise RuntimeError(receiver_error[-1])

                raise RealtimeUnavailable("Realtime STT session did not become ready.")



            self._clear_audio_queue()

            blocksize = 1200  # 50 ms at 24 kHz

            calibration_window = 0.15

            started = time.monotonic()

            speech_started = False

            last_speech_at = None

            pre_speech_chunks: list[bytes] = []

            noise_samples: list[float] = []



            with sd.RawInputStream(

                samplerate=24000,

                blocksize=blocksize,

                dtype="int16",

                channels=1,

                callback=self._audio_callback,

            ):

                while True:

                    if cancel_event is not None and cancel_event.is_set():

                        raise RuntimeError("Voice capture cancelled.")



                    elapsed = time.monotonic() - started

                    if not speech_started and elapsed >= wait_timeout:

                        raise RuntimeError(

                            "No speech detected. Check microphone permissions and speak after activating NEXUS."

                        )

                    if speech_started and elapsed >= maximum_recording_time:

                        break



                    try:

                        data = self.audio_queue.get(timeout=0.08)

                    except queue.Empty:

                        if receiver_error:

                            raise RuntimeError(receiver_error[-1])

                        continue



                    level = self._rms_level(data)

                    if not speech_started:

                        pre_speech_chunks.append(data)

                        max_pre = 5  # 250 ms

                        if len(pre_speech_chunks) > max_pre:

                            pre_speech_chunks.pop(0)



                        if elapsed <= calibration_window:

                            noise_samples.append(level)



                        noise_floor = statistics.median(noise_samples) if noise_samples else 30.0

                        threshold = max(50.0, noise_floor * 1.60)

                        if elapsed >= 0.15 and level >= threshold:

                            speech_started = True

                            last_speech_at = time.monotonic()

                            for buffered in pre_speech_chunks:

                                ws.send(json.dumps({

                                    "type": "input_audio_buffer.append",

                                    "audio": __import__("base64").b64encode(buffered).decode("ascii"),

                                }))

                            pre_speech_chunks.clear()

                        else:

                            continue

                    else:

                        ws.send(json.dumps({

                            "type": "input_audio_buffer.append",

                            "audio": __import__("base64").b64encode(data).decode("ascii"),

                        }))



                    speaking_threshold = max(

                        43.0,

                        (statistics.median(noise_samples) if noise_samples else 24.0) * 1.35,

                    )

                    if level >= speaking_threshold:

                        last_speech_at = time.monotonic()

                    elif last_speech_at is not None and time.monotonic() - last_speech_at >= end_silence:

                        break



            ws.send(json.dumps({"type": "input_audio_buffer.commit"}))



            deadline = time.monotonic() + 8.0

            while not transcript_done.is_set() and time.monotonic() < deadline:

                if cancel_event is not None and cancel_event.is_set():

                    raise RuntimeError("Voice capture cancelled.")

                if receiver_error:

                    raise RuntimeError(receiver_error[-1])

                time.sleep(0.03)



            if receiver_error and not transcript_parts and not final_transcript:

                raise RuntimeError(receiver_error[-1])



            text = final_transcript[-1] if final_transcript else "".join(transcript_parts).strip()

            if not text:

                raise RuntimeError("The realtime recognizer returned no speech text.")



            return text, self.detect_language(text)

        except RealtimeUnavailable:

            raise

        except RuntimeError:

            raise

        except sd.PortAudioError as error:

            raise RuntimeError(f"The microphone could not be accessed: {error}") from error

        except Exception as error:

            # Transport/protocol failures can use the HTTP fallback.

            raise RealtimeUnavailable(f"Realtime STT stopped: {error}") from error

        finally:

            stop_receiver.set()

            try:

                ws.close()

            except Exception:

                pass



    # ============================================================

    # HTTP STT FALLBACK

    # ============================================================



    @classmethod

    def transcribe_audio(cls, wav_bytes: bytes, language="auto"):

        if not wav_bytes:

            raise RuntimeError("No audio was provided for transcription.")



        headers = cls._headers()

        session = cls._session()

        data = {

            "model": cls.HTTP_STT_MODEL,

            "response_format": "json",

            "prompt": (

                "Speech is addressed to a Windows desktop assistant named NEXUS. "

                "Preserve application names, commands, file paths, URLs, numbers and technical terms."

            ),

            "stream": "false",

        }

        language_code = cls._language_code(language)

        if language_code:

            data["language"] = language_code



        # The HTTP fallback is intentionally bounded and only used when the

        # realtime transport is unavailable.

        try:

            response = session.post(

                cls.STT_URL,

                headers=headers,

                data=data,

                files={"file": ("nexus.wav", wav_bytes, "audio/wav")},

                timeout=(6.0, 35.0),

            )

        except requests.RequestException as error:

            raise RuntimeError(f"Online speech recognition failed: {error}") from error



        if not response.ok:

            try:

                payload = response.json()

                message = payload.get("error", {}).get("message", response.text)

            except ValueError:

                message = response.text

            raise RuntimeError(

                f"Online speech recognition failed: {message or response.status_code}"

            )



        try:

            payload = response.json()

        except ValueError as error:

            raise RuntimeError("Online speech recognition returned invalid JSON.") from error



        text = str(payload.get("text", "")).strip()

        if not text:

            raise RuntimeError("Speech was captured, but the online recognizer returned no words.")



        return text, cls.detect_language(text)



    def listen(

        self,

        language="auto",

        *,

        wait_timeout=3.0,

        maximum_recording_time=12.0,

        end_silence=0.38,

        cancel_event: Optional[threading.Event] = None,

    ):

        # Realtime STT is the primary microphone path. Avoid a second capture

        # attempt on transport errors because that makes voice commands feel

        # twice as slow. The bounded HTTP path remains available through

        # transcribe_audio() for already-captured audio such as wake phrases.

        return self._listen_realtime(

            language,

            wait_timeout=wait_timeout,

            maximum_recording_time=maximum_recording_time,

            end_silence=end_silence,

            cancel_event=cancel_event,

        )



    # ============================================================

    # ONLINE TTS — STREAM PCM

    # ============================================================



    @classmethod
    def _clean_for_speech(cls, text):
        return _clean_for_speech_text(text)



    @classmethod

    def _tts_instructions(cls, language):

        language = str(language or "auto").strip().lower()

        if language == "auto":

            return (

                "Speak naturally and conversationally in the language of the input. "

                "Use clear pronunciation, relaxed pacing, natural pauses, and a confident desktop-assistant tone."

            )

        label = cls.LANGUAGE_LABELS.get(language, "the input language")

        return (

            f"Speak naturally and conversationally in {label}. "

            "Use clear pronunciation, relaxed pacing, natural pauses, and a confident desktop-assistant tone."

        )



    def speak(self, text, language="auto"):

        clean_text = self._clean_for_speech(text)

        if not clean_text:

            return



        headers = self._headers()

        payload = {

            "model": self.TTS_MODEL,

            "voice": self.TTS_VOICE,

            "input": clean_text[:4096],

            "instructions": self._tts_instructions(language),

            "response_format": "pcm",

            "stream_format": "audio",

        }



        session = self._session()

        try:

            with self._tts_lock:

                with session.post(

                    self.TTS_URL,

                    headers={**headers, "Content-Type": "application/json"},

                    json=payload,

                    stream=True,

                    timeout=(8.0, 90.0),

                ) as response:

                    if not response.ok:

                        try:

                            payload_error = response.json()

                            message = payload_error.get("error", {}).get("message", response.text)

                        except ValueError:

                            message = response.text

                        raise RuntimeError(f"Online text-to-speech failed: {message}")



                    self._play_pcm_stream(response.iter_content(chunk_size=4096), sample_rate=24000)

        except requests.RequestException as error:

            raise RuntimeError(f"Online text-to-speech failed: {error}") from error



    @staticmethod

    def _play_pcm_stream(chunks, *, sample_rate=24000):

        leftover = b""

        try:

            with sd.RawOutputStream(

                samplerate=sample_rate,

                channels=1,

                dtype="int16",

                blocksize=1200,

            ) as stream:

                for chunk in chunks:

                    if not chunk:

                        continue

                    data = leftover + chunk

                    if len(data) % 2:

                        leftover = data[-1:]

                        data = data[:-1]

                    else:

                        leftover = b""

                    if data:

                        stream.write(data)

        except sd.PortAudioError as error:

            raise RuntimeError(f"Audio playback failed: {error}") from error



    @classmethod

    def stop_speaking(cls):
        try:
            sd.stop()
        except Exception:
            pass
        active = cls._active_kokoro_queue
        if active is not None:
            active.stop()



    # ============================================================

    # LANGUAGE / DEVICE HELPERS

    # ============================================================



    @classmethod

    def detect_language(cls, text):

        text = str(text or "").lower()

        scores = {code: 0 for code in cls.LANGUAGE_LABELS if code != "auto"}

        phrases = {

            "fr": ("bonjour", "merci", "s'il vous plaît", "je suis", "pourquoi", "est-ce que"),

            "sw": ("habari", "asante", "tafadhali", "unaweza", "naweza", "nisaidie"),

            "es": ("hola", "gracias", "por favor", "cómo estás", "puedes", "ayúdame"),

            "de": ("hallo", "danke", "bitte", "ich möchte", "kannst du", "was ist"),

            "it": ("ciao", "grazie", "per favore", "come stai", "puoi", "voglio"),

            "pt": ("olá", "obrigado", "por favor", "como você", "eu quero", "o que é"),

            "rw": ("muraho", "murakoze", "urakoze", "ndashaka", "mbwira", "nshobora", "wambwira"),

            "en": ("hello", "please", "thank you", "what is", "can you", "i need", "open chrome"),

        }

        for language, terms in phrases.items():

            for term in terms:

                if term in text:

                    scores[language] += 1



        words = set(re.findall(r"[\wÀ-ÿ']+", text, flags=re.UNICODE))

        word_terms = {

            "fr": {"avec", "pourquoi", "dans", "nous", "aider"},

            "sw": {"kwa", "hii", "yangu", "sawa", "huyu"},

            "es": {"que", "para", "una", "con", "ayuda"},

            "de": {"ich", "und", "für", "nicht", "eine", "hilfe"},

            "it": {"per", "una", "con", "non", "sono", "questo"},

            "pt": {"para", "uma", "com", "não", "ajuda"},

            "rw": {"ese", "gute", "hari", "ikibazo", "nshobora"},

        }

        for language, terms in word_terms.items():

            scores[language] += sum(1 for term in terms if term in words)



        best = max(scores, key=scores.get)

        return best if scores[best] > 0 else "en"



    def microphone_available(self):

        try:

            devices = sd.query_devices()

            return any(device.get("max_input_channels", 0) > 0 for device in devices)

        except Exception:

            return False



    def get_microphones(self):

        microphones = []

        try:

            devices = sd.query_devices()

            for device in devices:

                if device.get("max_input_channels", 0) > 0:

                    microphones.append(device.get("name", "Unknown microphone"))

        except Exception:

            pass

        return microphones
