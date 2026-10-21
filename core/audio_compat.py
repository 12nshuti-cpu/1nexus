"""Graceful stand-in used when the ``sounddevice``/PortAudio stack is unavailable.

Importing ``sounddevice`` raises ``OSError`` when PortAudio cannot be loaded.
Previously that crashed NEXUS at start-up. This shim lets the application
launch normally; any attempt to *use* audio raises a clear, catchable error.
"""
from __future__ import annotations


class AudioUnavailableError(RuntimeError):
    """Raised when audio input/output is requested but no audio backend loaded."""


class _PortAudioError(Exception):
    """Placeholder so ``except sd.PortAudioError`` clauses keep working."""


class MissingSoundDevice:
    PortAudioError = _PortAudioError
    available = False

    def __init__(self, cause: BaseException | None = None):
        self._cause = cause

    @property
    def reason(self) -> str:
        return f"Audio backend unavailable: {self._cause}" if self._cause else "Audio backend unavailable."

    def _fail(self, *_args, **_kwargs):
        raise AudioUnavailableError(self.reason)

    RawInputStream = RawOutputStream = InputStream = OutputStream = property(lambda self: self._fail)

    def query_devices(self, *args, **kwargs):
        raise AudioUnavailableError(self.reason)

    def stop(self, *args, **kwargs):  # stopping nothing is always safe
        return None
