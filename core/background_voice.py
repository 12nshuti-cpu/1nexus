from __future__ import annotations

import re
import threading
import time

from core.commands import CommandEngine
from core.voice import VoiceService
from core.wake_detector import WakeWordDetector
from config.settings import NEXUSSettings

class NexusBackgroundVoice:
    """Resident voice assistant: local wake detection, online command STT/TTS."""

    ACTIVATION_PHRASES = {"open", "open up"}

    def __init__(self, command_engine=None, on_activate=None, on_status=None):
        self.command_engine = command_engine or CommandEngine()
        self.on_activate = on_activate
        self.on_status = on_status
        self.stop_event = threading.Event()
        self.thread = None
        self.running = False
        self._service = VoiceService()
        self._wake_detector = WakeWordDetector(on_status=self._status)
        self._last_error_at = 0.0

    def start(self):
        preferences = NEXUSSettings()
        if not preferences.legacy_openai_voice_enabled:
            self._status("Legacy OpenAI background voice is disabled in Settings; use the Gemini Live microphone button instead.")
            return
        if not self._service.has_api_key():
            self._status("Legacy background voice needs its explicit Settings opt-in and an OpenAI API key.")
            return
        if self.running or (self.thread is not None and self.thread.is_alive()):
            return
        self.stop_event.clear()
        self.running = True
        self.thread = threading.Thread(target=self._run, name="NEXUS-Background-Voice", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        VoiceService.stop_speaking()
        current = self.thread
        if current and current.is_alive() and current is not threading.current_thread():
            current.join(timeout=1.0)
        self.running = False

    def _status(self, message):
        if callable(self.on_status):
            try:
                self.on_status(str(message))
            except Exception:
                pass

    def _run(self):
        try:
            if not self._service.microphone_available():
                self._status("Background voice could not find a microphone.")
                return
            if not self._service.has_api_key():
                self._status("Background voice is waiting for an OpenAI API key.")

            try:
                self._wake_detector.load(self._status)
            except Exception as error:
                self._status(str(error))
                return

            self._status("Background voice is ready. Listening locally for NEXUS.")
            while not self.stop_event.is_set():
                try:
                    wake_text, _wake_wav = self._wake_detector.wait_for_wake(self._service, self.stop_event)
                    if self.stop_event.is_set() or not wake_text:
                        break

                    normalized = self._normalize(wake_text)
                    after_wake = self._wake_detector.extract_after_wake(normalized)

                    # A bare wake word activates NEXUS without an API request.
                    if not after_wake and normalized in self._wake_detector.WAKE_PHRASES:
                        self._activate_and_speak("I'm here.")
                        continue

                    if after_wake:
                        # Wake phrase and command were captured together. Reuse that
                        # audio for one accurate online transcription instead of forcing
                        # the user to repeat the command into a second recording window.
                        online_text, language = self._service.transcribe_audio(_wake_wav, "auto")
                        command = self._extract_command_from_wake(online_text)
                    else:
                        self._speak("Yes?")
                        command_wav = self._service.capture_local_speech(
                            wait_timeout=2.5,
                            maximum_recording_time=8.0,
                            end_silence=0.42,
                            cancel_event=self.stop_event,
                        )
                        command, language = self._service.transcribe_audio(command_wav, "auto")

                    command = command.strip()
                    if not command:
                        continue

                    if self._is_activation_command(command):
                        self._activate_and_speak("I'm here.", language)
                        continue

                    self._status(f"NEXUS command: {command}")
                    response = self.command_engine.execute(command)
                    if response == "__OPEN_NEXUS__":
                        self._activate_and_speak("I'm here.", language)
                        continue
                    if response == "__CLEAR__":
                        response = "Activity console cleared."
                    self._speak(response, language)
                    self._status("Background voice command completed.")
                except Exception as error:
                    if self.stop_event.is_set():
                        break
                    now = time.monotonic()
                    if now - self._last_error_at > 3.0:
                        self._status(f"Background voice: {error}")
                        self._last_error_at = now
        finally:
            self.running = False
            self._status("Background voice stopped.")

    @staticmethod
    def _normalize(text):
        text = str(text or "").lower().strip()
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text)).strip()

    @classmethod
    def _extract_command_from_wake(cls, text):
        normalized = cls._normalize(text)
        prefixes = (
            "hey nexus", "hey nex us", "hey next us", "nexus", "nex us", "next us"
        )
        for prefix in prefixes:
            if normalized == prefix:
                return ""
            if normalized.startswith(prefix + " "):
                return normalized[len(prefix):].strip()
        return normalized

    @classmethod
    def _is_activation_command(cls, command):
        return cls._normalize(command) in cls.ACTIVATION_PHRASES

    def _activate_and_speak(self, text, language="auto"):
        if callable(self.on_activate):
            try:
                self.on_activate()
            except Exception:
                pass
        self._speak(text, language)

    def _speak(self, text, language="auto"):
        if not text or self.stop_event.is_set():
            return
        try:
            self._service.speak(text, language)
        except Exception as error:
            self._status(f"Voice output unavailable: {error}")
