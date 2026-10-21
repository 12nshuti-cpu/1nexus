"""Regression tests for the NEXUS <-> Kokoro worker JSON-lines protocol.

The real ``kokoro`` package prints a warning to *stdout* when a pipeline is created. That used to
land between protocol lines and break speech for every user. These tests run the real worker script
in a subprocess against a fake ``kokoro`` that behaves the same way.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from core.speech import KokoroError, KokoroHelper

WORKER = Path(__file__).resolve().parents[1] / "core" / "kokoro_tts_worker.py"

FAKE_KOKORO = textwrap.dedent('''
    import numpy as np

    class KPipeline:
        def __init__(self, lang_code="a", repo_id=None):
            # exactly what the real package does:
            print("WARNING: Defaulting repo_id to hexgrad/Kokoro-82M. Pass repo_id to suppress this warning.")
            self.repo_id = repo_id

        def __call__(self, text, voice="af_heart", speed=1.0):
            print("noisy progress output")
            yield "g", "p", np.zeros(2400, dtype=np.float32)
''')
FAKE_SOUNDFILE = textwrap.dedent('''
    def write(path, data, rate, subtype=None):
        open(path, "wb").write(b"RIFF0000WAVE")
''')


@pytest.fixture()
def helper(tmp_path, monkeypatch):
    (tmp_path / "kokoro.py").write_text(FAKE_KOKORO)
    (tmp_path / "soundfile.py").write_text(FAKE_SOUNDFILE)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    h = KokoroHelper(Path(sys.executable), WORKER, log_path=tmp_path / "worker.log",
                     startup_timeout=60, request_timeout=60)
    yield h
    h.stop()


def test_library_prints_do_not_corrupt_the_protocol(helper):
    reply = helper.request({"text": "Hello there", "lang": "a", "voice": "af_heart", "speed": 1.0})
    assert reply["ok"] and Path(reply["path"]).is_file()


def test_several_requests_reuse_one_worker_process(helper):
    first = helper.request({"text": "One", "lang": "a", "voice": "af_heart"})
    pid = helper._process.pid
    second = helper.request({"text": "Two", "lang": "a", "voice": "af_heart"})
    assert first["ok"] and second["ok"] and helper._process.pid == pid


def test_invalid_requests_are_rejected_without_killing_the_worker(helper):
    for bad in ({"text": "x", "lang": "zz"}, {"text": "x", "voice": "../../etc/passwd"}, {"text": "x" * 6000}):
        with pytest.raises(KokoroError):
            helper.request(bad)
    assert helper.running
    assert helper.request({"text": "still fine", "lang": "a", "voice": "af_heart"})["ok"]


def test_helper_skips_stray_non_json_lines():
    h = KokoroHelper(Path(sys.executable), WORKER)
    import queue

    h._lines = queue.Queue()
    for line in ("WARNING: something\n", "\n", "[1, 2]\n", '{"ok": true, "path": "x.wav"}\n'):
        h._lines.put(line)
    assert h._next_message(5) == {"ok": True, "path": "x.wav"}


def test_helper_times_out_instead_of_hanging_on_noise_only():
    h = KokoroHelper(Path(sys.executable), WORKER)
    import queue

    h._lines = queue.Queue()
    h._lines.put("only noise\n")
    with pytest.raises(KokoroError):
        h._next_message(0.3)


def test_network_failures_explain_the_first_run_download():
    import importlib.util

    spec = importlib.util.spec_from_file_location("kokoro_tts_worker", WORKER)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    message = worker.describe_error(RuntimeError("403 Forbidden"))
    assert "403 Forbidden" in message and "internet" in message
    assert worker.describe_error(ValueError("Invalid voice name")) == "Invalid voice name"
