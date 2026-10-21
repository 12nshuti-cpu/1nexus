"""Headless smoke tests for the real Qt interface (QT_QPA_PLATFORM=offscreen).

These do not replace manual testing on Windows, but they catch the failures that
otherwise only show up when a user launches the app: import errors, broken
constructors, duplicated handlers and shutdown crashes.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


@pytest.fixture()
def window(qapp, track):
    from ui.main_window import MainWindow

    win = track(MainWindow())
    win.show()
    qapp.processEvents()
    return win


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


def test_main_window_shutdown_is_idempotent(qapp, track):
    from ui.main_window import MainWindow

    win = track(MainWindow())
    win.shutdown()
    win.shutdown()  # a second call (e.g. aboutToQuit after closeEvent) must not raise


def test_first_run_wizard_constructs(qapp, settings, track):
    from ui.first_run_wizard import FirstRunWizard

    wizard = track(FirstRunWizard(settings))
    wizard.show()
    qapp.processEvents()
    assert wizard.isVisible()


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
def test_settings_page_saves_speech_input_choices(qapp, settings, monkeypatch, track):
    from PySide6.QtWidgets import QMessageBox

    from ui.settings_page import SettingsPage

    shown = []  # save_settings ends with a modal "Settings saved" box, which would block headless
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append("WARNING: " + str(a[2:])))
    page = track(SettingsPage(settings))
    page.show()
    qapp.processEvents()
    page.stt_model.setCurrentIndex(page.stt_model.findData("small.en"))
    page.push_to_talk.setChecked(True)
    page.save_settings()
    assert settings.stt_model == "small.en" and settings.push_to_talk is True
    assert len(shown) == 1 and "have been saved" in shown[0]  # saved cleanly, no warning dialog


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


# ----------------------------------------------------------- document summary flow
def _messages(window):
    return window.conversation_manager.get_messages(window.current_conversation_id)


def test_summarize_command_reads_the_file_and_stores_the_summary(window, qapp, tmp_path, monkeypatch):
    doc = tmp_path / "notes.txt"
    doc.write_text("Budget meeting moved to Friday. Bring the Q3 numbers.", encoding="utf-8")
    seen = {}

    def fake_summarize(name, text, truncated=False, total_chars=0):
        seen.update(name=name, text=text)
        return "Meeting is on Friday.", "test-model (on this PC)"

    monkeypatch.setattr(window.command_engine.ai, "summarize_document", fake_summarize)
    window.process_command(f"summarize {doc}")
    window.document_worker.wait(10000)
    qapp.processEvents()

    assert seen["name"] == "notes.txt" and "Budget meeting" in seen["text"]
    roles = [(m["role"], m["content"]) for m in _messages(window)]
    assert roles[0] == ("user", "Summarize the document: notes.txt")
    assert roles[-1][0] == "assistant" and "Meeting is on Friday." in roles[-1][1]


def test_summarize_missing_file_reports_the_problem_truthfully(window, qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(window.command_engine.ai, "summarize_document",
                        lambda *a, **k: pytest.fail("the model must not be called for a missing file"))
    window.process_command(f"summarize {tmp_path / 'ghost.txt'}")
    window.document_worker.wait(10000)
    qapp.processEvents()
    last = _messages(window)[-1]
    assert last["role"] == "assistant" and "could not find" in last["content"]


def test_summarize_model_failure_is_reported_not_hidden(window, qapp, tmp_path, monkeypatch):
    doc = tmp_path / "a.txt"
    doc.write_text("hello", encoding="utf-8")

    def broken(*a, **k):
        raise RuntimeError("Ollama is not running")

    monkeypatch.setattr(window.command_engine.ai, "summarize_document", broken)
    window.process_command(f"summarize {doc}")
    window.document_worker.wait(10000)
    qapp.processEvents()
    last = _messages(window)[-1]["content"]
    assert "could not summarise" in last and "Ollama is not running" in last
    assert "ERROR" in window.assistant_status.text()


def test_window_closes_cleanly_while_a_summary_is_running(qapp, tmp_path, monkeypatch, track):
    import threading

    from ui.main_window import MainWindow

    doc = tmp_path / "a.txt"
    doc.write_text("hello", encoding="utf-8")
    release = threading.Event()
    win = track(MainWindow())
    monkeypatch.setattr(win.command_engine.ai, "summarize_document",
                        lambda *a, **k: (release.wait(5) and "late", "m"))
    win.process_command(f"summarize {doc}")
    win.shutdown()          # must not hang or crash even though the worker is still busy
    release.set()


# ------------------------------------------------------- microphone list is lazy and non-destructive
def test_settings_page_does_not_query_audio_devices_while_building(qapp, settings, monkeypatch, track):
    from core import stt
    from ui.settings_page import SettingsPage

    calls = []
    monkeypatch.setattr(stt, "list_input_devices", lambda: calls.append(1) or [(2, "USB Mic")])
    page = track(SettingsPage(settings))
    assert calls == []            # nothing asked of the audio drivers during construction
    page.show()
    qapp.processEvents()
    assert calls == [1] and page.microphone.findData(2) >= 0


def test_saving_settings_never_wipes_a_saved_microphone(qapp, settings, monkeypatch, track):
    from PySide6.QtWidgets import QMessageBox

    from core import stt
    from ui.settings_page import SettingsPage

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    settings.microphone_device = 5
    # 1) page saved without ever being shown -> stored device untouched
    page = track(SettingsPage(settings))
    page.save_settings()
    assert settings.microphone_device == 5
    # 2) shown while the device is unplugged -> still offered, still saved
    monkeypatch.setattr(stt, "list_input_devices", lambda: [])
    page2 = track(SettingsPage(settings))
    page2.show()
    qapp.processEvents()
    assert page2.microphone.currentData() == 5
    page2.save_settings()
    assert settings.microphone_device == 5
