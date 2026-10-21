"""Headless smoke tests for the real Qt interface (QT_QPA_PLATFORM=offscreen).

These do not replace manual testing on Windows, but they catch the failures that
otherwise only show up when a user launches the app: import errors, broken
constructors, duplicated handlers and shutdown crashes.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


@pytest.fixture()
def window(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    qapp.processEvents()
    yield win
    win.shutdown()
    win.close()
    qapp.processEvents()


def test_main_window_starts_and_has_core_controls(window):
    assert window.windowTitle() == "NEXUS"
    assert window.isVisible()
    assert hasattr(window, "command_engine")


def test_main_window_handles_resize_across_compact_and_wide_layouts(window, qapp):
    for width, height in ((900, 640), (1100, 700), (1400, 860)):
        window.resize(width, height)
        qapp.processEvents()
    assert window.width() >= 900


def test_main_window_defines_resize_handler_once():
    """Regression: a second resizeEvent used to shadow the first silently."""
    import inspect

    from ui import main_window

    source = inspect.getsource(main_window.MainWindow)
    assert source.count("def resizeEvent(") == 1


def test_main_window_shutdown_is_idempotent(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    win.shutdown()
    win.shutdown()  # a second call (e.g. aboutToQuit after closeEvent) must not raise


def test_first_run_wizard_constructs(qapp, settings):
    from ui.first_run_wizard import FirstRunWizard

    wizard = FirstRunWizard(settings)
    wizard.show()
    qapp.processEvents()
    assert wizard.isVisible()
    wizard.close()


def test_settings_page_imports():
    from ui import settings_page  # noqa: F401


def test_selftest_flag_passes_in_a_fresh_process(tmp_path):
    """`app.py --selftest` is what scripts/build.ps1 runs against the frozen exe."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    env = dict(
        os.environ,
        NEXUS_DATA_DIR=str(tmp_path / "data"),
        XDG_CONFIG_HOME=str(tmp_path / "cfg"),
        XDG_DATA_HOME=str(tmp_path / "xdg"),
        HOME=str(tmp_path / "home"),
        NEXUS_DISABLE_KEYRING="1",
        QT_QPA_PLATFORM="offscreen",
    )
    (tmp_path / "home").mkdir()
    result = subprocess.run(
        [sys.executable, str(root / "app.py"), "--selftest"],
        cwd=root, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-800:]
    assert "SELFTEST OK" in result.stdout


# ------------------------------------------------------------------ voice input wiring
def test_settings_page_saves_speech_input_choices(qapp, settings, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from ui.settings_page import SettingsPage

    shown = []  # save_settings ends with a modal "Settings saved" box, which would block headless
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append("WARNING: " + str(a[2:])))
    page = SettingsPage(settings)
    page.show()
    qapp.processEvents()
    page.stt_model.setCurrentIndex(page.stt_model.findData("small.en"))
    page.push_to_talk.setChecked(True)
    page.save_settings()
    assert settings.stt_model == "small.en" and settings.push_to_talk is True
    assert len(shown) == 1 and "have been saved" in shown[0]  # saved cleanly, no warning dialog
    page.close()


@pytest.mark.parametrize("engine,key,expected", [
    ("local", False, "local"), ("local", True, "local"),
    ("automatic", False, "local"), ("automatic", True, "gemini"),
    ("online", False, "gemini"), ("online", True, "gemini"),
])
def test_voice_route_selection(monkeypatch, engine, key, expected):
    from core import gemini_engine
    from ui.main_window import VoiceCaptureWorker

    monkeypatch.setattr(gemini_engine, "gemini_is_configured", lambda: key)
    assert VoiceCaptureWorker.route(engine) == expected


def _run_worker(qapp, monkeypatch, settings, audio, transcribe_result=("", "en"), **kw):
    from core import stt
    from ui.main_window import VoiceCaptureWorker

    class FakeRecorder:
        def __init__(self, **_k):
            pass

        def record(self):
            return audio

        def finish(self):
            pass

        def cancel(self):
            pass

    class FakeTranscriber:
        def __init__(self, *_a, **_k):
            pass

        def transcribe(self, _audio, _language="auto"):
            return transcribe_result

    monkeypatch.setattr(stt, "MicrophoneRecorder", FakeRecorder)
    monkeypatch.setattr(stt, "LocalTranscriber", FakeTranscriber)
    worker = VoiceCaptureWorker("auto", "local", [], None, settings=settings)
    got = {"captured": [], "failed": []}
    worker.captured.connect(lambda text, lang: got["captured"].append((text, lang)))
    worker.failed.connect(got["failed"].append)
    worker.run()  # run synchronously: the thread behaviour itself is Qt's job
    return got


def test_local_voice_turn_emits_transcript(qapp, monkeypatch, settings):
    import numpy as np

    got = _run_worker(qapp, monkeypatch, settings, np.ones(16000, dtype=np.float32), ("what time is it", "en"))
    assert got["captured"] == [("what time is it", "en")] and not got["failed"]


def test_local_voice_turn_reports_silence_not_an_error(qapp, monkeypatch, settings):
    got = _run_worker(qapp, monkeypatch, settings, None)
    assert got["captured"] and got["captured"][0][0].startswith("No speech detected") and not got["failed"]


def test_local_voice_turn_reports_unintelligible_audio(qapp, monkeypatch, settings):
    import numpy as np

    got = _run_worker(qapp, monkeypatch, settings, np.ones(16000, dtype=np.float32), ("", "en"))
    assert got["captured"][0][0].startswith("No speech detected")


def test_local_voice_turn_surfaces_recognition_errors(qapp, monkeypatch, settings):
    import numpy as np
    from core import stt
    from ui.main_window import VoiceCaptureWorker

    class BrokenRecorder:
        def __init__(self, **_k):
            pass

        def record(self):
            raise stt.SttError("No microphone was found.")

    monkeypatch.setattr(stt, "MicrophoneRecorder", BrokenRecorder)
    worker = VoiceCaptureWorker("auto", "local", [], None, settings=settings)
    failures = []
    worker.failed.connect(failures.append)
    worker.run()
    assert failures == ["No microphone was found."]
