"""Headless tests for the redesigned interface: navigation, theming, chat rendering and the
Reminders / Memory screens (which must read and write the same stores the assistant uses)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402


@pytest.fixture()
def window(qapp, track):
    from ui.main_window import MainWindow

    win = track(MainWindow())
    win.show()
    qapp.processEvents()
    if win.system_check_overlay is not None:
        win.finish_system_check()
    return win


# ------------------------------------------------------------------ navigation & layout
def test_every_page_is_reachable_and_old_names_still_work(window, qapp):
    for name in window.PAGES:
        window.switch_page(name)
        qapp.processEvents()
        assert window.page_stack.currentWidget() is window.pages[name]
        assert window.nav_buttons[name].isChecked()
    for old, new in (("dashboard", "home"), ("assistant", "chat"), ("conversations", "chat")):
        window.switch_page(old)
        assert window.page_stack.currentWidget() is window.pages[new]


def test_sidebar_collapses_on_narrow_windows_and_on_request(window, qapp):
    window.resize(1300, 800)
    qapp.processEvents()
    assert window.sidebar.width() == 264 and window.history_section.isVisible()
    window.resize(900, 640)
    qapp.processEvents()
    assert window.sidebar.width() == 68 and not window.history_section.isVisible()
    window.resize(1300, 800)
    qapp.processEvents()
    window.toggle_sidebar()
    assert window.sidebar.width() == 68
    window.toggle_sidebar()
    assert window.sidebar.width() == 264


def test_theme_and_accent_apply_and_persist(window, qapp):
    from ui.theme import current_palette

    window.set_theme_mode("light")
    assert current_palette().mode == "light" and window.settings.get("ui_theme") == "light"
    assert "#f4f6fa" in qapp.styleSheet()
    window.apply_accent_color("#8b7bff")
    assert current_palette().accent == "#8b7bff" and window.settings.get("ui_accent") == "#8b7bff"
    window.toggle_theme()
    assert current_palette().mode == "dark"
    window.apply_reset_preferences()
    assert current_palette().accent == "#45d9ff"


def test_palettes_keep_text_readable():
    from PySide6.QtGui import QColor

    from ui.theme import ACCENT_PRESETS, build_palette, contrast

    for mode in ("dark", "light"):
        for _name, accent in ACCENT_PRESETS:
            p = build_palette(mode, accent)
            assert contrast(QColor(p.text), QColor(p.bg)) >= 7
            assert contrast(QColor(p.text_2), QColor(p.surface)) >= 4.5
            assert contrast(QColor(p.accent_text), QColor(p.surface)) >= 4.5
            assert contrast(QColor(p.on_accent), QColor(p.accent)) >= 3


# ------------------------------------------------------------------ chat
def test_status_pill_accepts_legacy_status_strings(qapp):
    from ui.components import StatusPill

    pill = StatusPill()
    pill.setText("● THINKING")
    assert pill.state == "thinking" and pill.text() == "● THINKING"
    pill.setText("● ERROR")
    assert pill.state == "error" and "ERROR" in pill.text()


def test_chat_view_appends_messages_and_streams_without_rebuilding(window, qapp):
    cm = window.conversation_manager
    cid = cm.create_conversation()
    cm.add_message(cid, "user", "Hello")
    cm.add_message(cid, "assistant", "Hi! **How** can I help?")
    window.load_conversation(cid)
    qapp.processEvents()
    view = window.assistant_output
    assert view.message_count() == 2 and not view.empty.isVisible()
    first = view._widgets[0]

    window.streaming_ai_responses[cid] = "Partial ans"
    window.render_current_conversation()
    assert view._live is not None and "Partial ans" in view._live.content
    assert view._widgets[0] is first          # earlier messages are not rebuilt per chunk

    window.streaming_ai_responses.pop(cid)
    cm.add_message(cid, "assistant", "Partial answer, finished.")
    window.render_current_conversation()
    assert view._live is None and view.message_count() == 3 and view._widgets[0] is first


def test_empty_chat_shows_suggestions_and_new_chat_resets(window, qapp):
    window.start_new_conversation()
    qapp.processEvents()
    assert window.current_conversation_id is None
    assert window.assistant_output.empty.isVisible()
    assert window.page_stack.currentWidget() is window.pages["chat"]


def test_local_command_from_home_answers_in_chat(window, qapp):
    window.switch_page("home")
    window.handle_dashboard_command("help")
    qapp.processEvents()
    assert window.page_stack.currentWidget() is window.pages["chat"]
    messages = window.conversation_manager.get_messages(window.current_conversation_id)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert window.assistant_output.message_count() == 2


def test_attachment_is_shown_on_both_composers_and_cleared(window):
    window.dashboard_attachment = {"name": "notes.txt", "content": "x"}
    for composer in (window.home_composer, window.chat_composer):
        composer.set_attachment("notes.txt")
    window.clear_dashboard_attachment()
    assert window.dashboard_attachment is None
    assert not window.home_composer.attachment_chip.isVisibleTo(window.home_composer)
    assert not window.chat_composer.attachment_chip.isVisibleTo(window.chat_composer)


def test_voice_states_drive_the_orb_and_voice_bar(window, qapp):
    window.switch_page("chat")
    for state in ("listening", "thinking", "speaking"):
        window.set_core_state(state)
        assert window.dashboard_core_widget.state == state
        assert window.voice_bar.isVisibleTo(window.assistant_page)
    window.set_core_state("sleeping")
    assert not window.voice_bar.isVisibleTo(window.assistant_page)
    assert window.orb_state_label.text() == "Ready when you are"


def test_voice_output_toggle_is_shared_by_both_composers(window):
    window.set_voice_mode(True)
    assert window.voice_toggle.isChecked() and window.assistant_voice_toggle.isChecked()
    window.assistant_voice_toggle.click()
    assert window.voice_enabled is False and not window.voice_toggle.isChecked()


# ------------------------------------------------------------------ reminders & memory screens
def test_reminders_page_adds_with_natural_language_and_completes(window, qapp):
    page = window.reminders_page
    page.input.setText("water the plants in 20 minutes")
    page.add_from_input()
    reminders = window.command_engine.assistant.reminders.list()
    assert [r.message for r in reminders] == ["water the plants"]
    due = reminders[0].due_at
    assert timedelta(minutes=19) < due - datetime.now() < timedelta(minutes=21)
    page._complete(reminders[0].id)
    assert window.command_engine.assistant.reminders.list() == []


def test_reminders_page_explains_unparseable_times(window):
    page = window.reminders_page
    page.input.setText("water the plants")
    page.add_from_input()
    assert window.command_engine.assistant.reminders.list() == []
    assert "couldn't work out when" in page.feedback.text()


def test_reminder_created_in_chat_appears_on_home_and_reminders(window, qapp):
    window.process_command("remind me to call Sam in 10 minutes")
    window._refresh_data_views()
    qapp.processEvents()
    assert any(r.message == "call Sam" for r in window.reminders_page.upcoming())
    titles = [w.full_text() for w in window.home_reminders_card.findChildren(type(window.current_conversation_title_label))]
    assert "call Sam" in titles


def test_memory_page_adds_searches_and_deletes(window, qapp):
    page = window.memory_page
    page.input.setText("remember that my sister is Aline")
    page.add_from_input()
    store = window.command_engine.assistant.memory
    memories = store.list()
    assert [m.content for m in memories] == ["my sister is Aline"]
    page.search.setText("Aline")
    page._delete(memories[0])
    assert store.list() == []


def test_activity_page_lists_events(window, qapp):
    window.add_activity("Reminder: stretch")
    window.switch_page("activity")
    qapp.processEvents()
    texts = [label.text() for label in window.activity_page.findChildren(type(window.orb_state_label))]
    assert "Reminder: stretch" in texts


def test_microphone_turn_updates_the_ui_and_answers_in_chat(window, qapp, monkeypatch):
    """Press the mic, 'say' help, and check the listening UI appears and then clears."""
    import time

    import numpy as np

    from core import stt

    class FakeRecorder:
        def __init__(self, **_k):
            pass

        def record(self):
            time.sleep(0.3)
            return np.ones(16000, dtype=np.float32)

        def finish(self):
            pass

        def cancel(self):
            pass

    class FakeTranscriber:
        def __init__(self, *_a, **_k):
            pass

        def transcribe(self, _audio, _language="auto"):
            return "help", "en"

    monkeypatch.setattr(stt, "MicrophoneRecorder", FakeRecorder)
    monkeypatch.setattr(stt, "LocalTranscriber", FakeTranscriber)
    window.settings.ai_engine = "local"
    monkeypatch.setattr(window, "speak_response", lambda *a, **k: None)
    window.switch_page("chat")
    window.assistant_mic_button.click()
    qapp.processEvents()
    assert window.dashboard_core_widget.state == "listening"
    assert window.assistant_mic_button.property("listening") == "true"
    assert window.voice_bar.isVisibleTo(window.assistant_page)
    window.voice_worker.wait(5000)
    deadline = time.time() + 5
    while time.time() < deadline and window.assistant_mic_button.property("listening") == "true":
        qapp.processEvents()
    assert window.assistant_mic_button.property("listening") == "false"
    messages = window.conversation_manager.get_messages(window.current_conversation_id)
    assert messages[0]["content"] == "help" and messages[-1]["role"] == "assistant"
    assert window.voice_enabled  # speaking to NEXUS turns spoken replies on for the session


def test_streamed_ai_reply_renders_live_and_is_kept(window, qapp, monkeypatch):
    """A streamed answer (on the real AI worker thread) shows live, then stays as one message."""
    import time

    def fake_stream(message, conversation=None, on_chunk=None, on_speech_chunk=None):
        text = ""
        for i in range(6):
            time.sleep(0.05)
            piece = f"- point {i} about water.\n"
            text += piece
            if on_chunk:
                on_chunk(piece)
        return text

    monkeypatch.setattr(window.command_engine.ai, "ask_stream", fake_stream)
    window.process_command("tell me about water")
    seen_live = False
    deadline = time.time() + 10
    while time.time() < deadline and window.pending_ai_requests:
        qapp.processEvents()
        seen_live = seen_live or window.assistant_output._live is not None
        time.sleep(0.01)
    qapp.processEvents()
    assert seen_live and window.pending_ai_requests == 0
    assert window.assistant_output._live is None
    assert window.assistant_output.message_count() == 2
    assert "point 5" in window.assistant_output._widgets[-1].content


# ------------------------------------------------------------------ design review follow-ups
def test_chat_history_is_grouped_by_day_and_search_hides_empty_groups(window, qapp):
    cm = window.conversation_manager
    first = cm.create_conversation()
    cm.update_title(first, "Holiday plans")
    cm.add_message(first, "user", "Where should we go?")
    second = cm.create_conversation()
    cm.update_title(second, "Budget questions")
    cm.add_message(second, "user", "How much can I save?")
    window.refresh_conversation_list()
    items = [window.conversation_list.item(i) for i in range(window.conversation_list.count())]
    headers = [i for i in items if i.data(Qt.UserRole + 2) == "header"]
    assert len(headers) == 1 and items[0] in headers            # one "Today" heading first
    window.search_input.setText("holiday")
    qapp.processEvents()
    visible = [i.data(Qt.UserRole + 1) for i in items if not i.isHidden() and i.data(Qt.UserRole)]
    assert visible == ["Holiday plans"] and not headers[0].isHidden()
    window.search_input.setText("nothing matches this")
    assert headers[0].isHidden()
    window.search_input.clear()


def test_settings_switches_have_one_label_that_toggles_them(qapp, settings, track):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QLabel

    from ui.settings_page import SettingsPage

    page = track(SettingsPage(settings))
    switch = page.execution_enabled
    assert switch.text() == "" and "shell command execution" in switch.toolTip().lower()
    label = next(lbl for lbl in page.findChildren(QLabel) if lbl.text() == "Execution")
    before = switch.isChecked()
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        QApplication.sendEvent(label, QMouseEvent(kind, QPointF(2, 2), QPointF(2, 2), Qt.LeftButton,
                                                  Qt.LeftButton, Qt.NoModifier))
    assert switch.isChecked() is (not before)


def test_app_icon_and_ico_file_come_from_the_same_mark(tmp_path, qapp):
    from PySide6.QtGui import QIcon

    from ui.brand import ICON_SIZES, app_icon, write_ico

    icon = app_icon("#45d9ff")
    assert not icon.isNull() and icon.availableSizes()
    target = tmp_path / "nexus.ico"
    write_ico(target)
    loaded = QIcon(str(target))
    assert {s.width() for s in loaded.availableSizes()} == set(ICON_SIZES)


def test_home_orb_scales_with_window_height(window, qapp):
    window.resize(1300, 900)
    qapp.processEvents()
    tall = window.dashboard_core_widget.width()
    window.resize(1300, 600)
    qapp.processEvents()
    assert window.dashboard_core_widget.width() < tall


class _FakeVoice:
    """Stands in for the speech manager: the test decides how far the voice has got."""

    def __init__(self):
        self.queued = []
        self.words = 0
        self.done = False
        self.busy = False
        self.last_error = ""
        self.last_engine = "Natural voice"

    def enqueue(self, text, language="auto", tag=None):
        self.queued.append((text, tag))
        return True

    def spoken_words(self, tag):
        return self.words

    def is_speaking(self, tag):
        return bool(self.queued) and not self.done

    def forget(self, tag):
        pass

    def pop_notice(self):
        return ""

    def stop(self):
        self.done = True

    def close(self):
        pass


def test_spoken_reply_appears_word_by_word_as_it_is_said(window, qapp, monkeypatch):
    import time

    seen = {}

    def fake_stream(message, conversation=None, on_chunk=None, on_speech_chunk=None, spoken=False):
        seen["spoken"] = spoken
        text = "Sure, it is sunny today. Enjoy the walk."
        on_chunk(text)
        on_speech_chunk("Sure, it is sunny today.")
        on_speech_chunk("Enjoy the walk.")
        return text

    voice = _FakeVoice()
    window.kokoro_speech_queue = voice
    window.voice_enabled = True
    window.settings.reveal_text_with_voice = True
    monkeypatch.setattr(window.command_engine.ai, "ask_stream", fake_stream)
    window.process_command("what's the weather like")
    deadline = time.time() + 10
    while time.time() < deadline and window.pending_ai_requests:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    chat = window.assistant_output
    assert seen["spoken"] is True                           # the model was asked to talk, not write
    assert [tag for _text, tag in voice.queued] == ["reply-1", "reply-1"]
    assert chat.message_count() == 1 and chat._live is None  # nothing shown before the voice starts

    voice.words = 3
    end = time.time() + 2
    while time.time() < end and (chat._live is None or "is" not in chat._live.content):
        qapp.processEvents()
        time.sleep(0.02)
    assert chat._live is not None and chat._live.content == "Sure, it is"

    voice.done = True
    end = time.time() + 2
    while time.time() < end and window.voice_reveals:
        qapp.processEvents()
        time.sleep(0.02)
    qapp.processEvents()
    assert not window.voice_reveals and chat._live is None
    assert chat.message_count() == 2 and "Enjoy the walk." in chat._widgets[-1].content


def test_stopping_the_voice_shows_the_whole_reply(window, qapp):
    voice = _FakeVoice()
    window.kokoro_speech_queue = voice
    window.voice_enabled = True
    window.process_command("time")       # a local command, answered and spoken at once
    qapp.processEvents()
    assert window.voice_reveals and window.assistant_output._live is None
    window.voice_output_active = True
    from core.voice import VoiceService
    VoiceService._active_kokoro_queue = voice
    assert window.interrupt_voice_output()
    qapp.processEvents()
    assert not window.voice_reveals
    assert window.assistant_output.message_count() == 2


def test_text_shows_at_once_when_reveal_is_switched_off(window, qapp):
    voice = _FakeVoice()
    window.kokoro_speech_queue = voice
    window.voice_enabled = True
    window.settings.reveal_text_with_voice = False
    window.process_command("time")
    qapp.processEvents()
    assert not window.voice_reveals and voice.queued
    assert window.assistant_output.message_count() == 2
