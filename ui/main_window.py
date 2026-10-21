"""The NEXUS main window.

Layout: a sidebar (navigation + conversation history) and a stack of pages: Home, Chat,
Reminders, Memory, System, Activity and Settings. Presentation lives here and in
``ui.components`` / ``ui.pages``; AI, speech, shell and storage work is done by ``core``
and always runs off the UI thread.
"""
from html import escape  # noqa: I001
import os
import platform
import socket
import subprocess
import threading
import time
import shutil
from pathlib import Path

try:
    import psutil
except Exception:  # noqa: BLE001
    psutil = None

from PySide6.QtCore import (
    Qt,
    QThread,
    QTimer,
    QObject,
    QProcess,
    Signal,
    QSize,
)

from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCursor

from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QMessageBox,
    QMenu,
    QProgressBar,
)

from config.settings import NEXUSSettings, open_qsettings
from core.ai_worker import AIWorker
from core.commands import CommandEngine
from core.conversation_manager import ConversationManager
from core.system_monitor import SystemMonitor
from core.system_check import NEXUSSystemChecker
from core.voice_worker import VoiceSpeakWorker
from core.shell_worker import ShellCommandWorker
from config import settings as nexus_settings
from ui.components import (
    Card,
    ChatView,
    Composer,
    ElidedLabel,
    EmptyState,
    FlowLayout,
    IconButton,
    IconLabel,
    NavButton,
    NexusOrb,
    OrbMark,
    ResponsiveGrid,
    Segmented,
    Sparkline,
    StatusPill,
    TerminalInput,
    Toast,
    UsageGraph,
    VoiceBar,
    fade_in,
    friendly_time,
    make_icon,
    repolish,
)
from ui.pages import ActivityPage, MemoryPage, PageHeader, RemindersPage, activity_icon, scroll_page
from ui.system_check_dialog import SystemCheckDialog
from ui.settings_page import SettingsPage
from ui.theme import ACCENT_PRESETS, DEFAULT_ACCENT, STATE_COLORS, current_palette, theme

__all__ = ["MainWindow", "TerminalInput", "VoiceCaptureWorker", "DocumentSummaryWorker"]

# Prompts offered on the home screen and in an empty chat. Each one is handled by a real
# NEXUS feature (local commands, the reminder parser, the calculator, document summaries).
SUGGESTIONS = (
    ("What can you do?", "help"),
    ("Remind me to stretch in 30 minutes", "remind me to stretch in 30 minutes"),
    ("How is my PC doing?", "system"),
    ("Summarize a document", "summarize this document"),
    ("Calculate 15% of 80", "calculate 15% of 80"),
    ("What time is it?", "What time is it?"),
)

ORB_TEXT = {
    "sleeping": ("Ready when you are", "Tap the orb or press Ctrl+M to talk, or type below."),
    "listening": ("Listening…", "Speak now. Tap the orb again when you finish, or press Esc to cancel."),
    "thinking": ("Thinking…", "Working on your request."),
    "speaking": ("Speaking…", "Tap the orb or press Esc to stop."),
}

class VoiceCaptureWorker(QThread):
    """Keeps microphone capture and speech recognition off the interface thread.

    Two routes, chosen by :meth:`route`:

    * ``local``  - record with the microphone, transcribe on this computer with
      faster-whisper, then hand the text to the normal NEXUS pipeline
      (``captured``). Tools, memory and the speech engine all apply.
    * ``gemini`` - the existing Gemini Live voice turn (online, needs a key).
    """

    captured = Signal(str, str)
    geminiCompleted = Signal(str, str, bytes)
    failed = Signal(str)
    status = Signal(str)

    NO_SPEECH = "No speech detected."

    def __init__(self, language="auto", engine="automatic", conversation=None, parent=None, settings=None):
        super().__init__(parent)
        self.language = str(language or "auto")
        self.engine = str(engine or "automatic")
        self.conversation = list(conversation or [])
        self.settings = settings
        self._recorder = None
        self._cancelled = False

    @staticmethod
    def route(engine):
        """'local' (on-device speech recognition) or 'gemini' (Gemini Live)."""
        from core.gemini_engine import gemini_is_configured

        engine = str(engine or "automatic")
        if engine == "local":
            return "local"
        if engine == "automatic" and not gemini_is_configured():
            return "local"
        return "gemini"

    # -- control from the UI thread ------------------------------------------
    def finish_listening(self):
        """Stop recording now and transcribe what was heard."""
        recorder = self._recorder
        if recorder is not None:
            recorder.finish()

    def cancel(self):
        """Stop recording and throw the audio away."""
        self._cancelled = True
        recorder = self._recorder
        if recorder is not None:
            recorder.cancel()

    # -- worker thread ----------------------------------------------------------
    def run(self):
        try:
            if self.route(self.engine) == "local":
                self._run_local()
            else:
                self._run_gemini()
        except Exception as error:  # noqa: BLE001
            self.failed.emit(str(error))

    def _run_local(self):
        from core.stt import EndpointConfig, LocalTranscriber, MicrophoneRecorder

        settings = self.settings
        push_to_talk = bool(settings.push_to_talk) if settings is not None else False
        device = settings.microphone_device if settings is not None else None
        model = settings.stt_model if settings is not None else "base"
        config = EndpointConfig(auto_stop=not push_to_talk, max_seconds=120.0 if push_to_talk else 30.0)

        self.status.emit("Listening - click the microphone again when you are done." if push_to_talk
                         else "Listening - just speak; I will stop when you pause.")
        self._recorder = MicrophoneRecorder(device=device, config=config)
        audio = self._recorder.record()
        self._recorder = None
        if audio is None:
            note = "Listening cancelled." if self._cancelled else ""
            self.captured.emit(f"{self.NO_SPEECH} {note}".strip(), "auto")
            return

        self.status.emit("Transcribing...")
        text, detected = LocalTranscriber(model, status=self.status.emit).transcribe(audio, self.language)
        if not text:
            self.captured.emit(self.NO_SPEECH, "auto")
            return
        self.captured.emit(text, self.language if self.language != "auto" else detected)

    def _run_gemini(self):
        from core.gemini_engine import GeminiUnavailable, gemini_is_configured, live_microphone_turn
        from config import settings as app_settings
        import asyncio

        if not gemini_is_configured():
            raise GeminiUnavailable(
                "Gemini Live voice needs an API key. Add it in Settings or set the GEMINI_API_KEY environment variable. "
                "Choose Automatic or Local mode to use on-device speech recognition instead."
            )
        transcript, answer, audio = asyncio.run(live_microphone_turn(
            app_settings.load_system_prompt(),
            self.conversation,
        ))
        if not answer:
            raise GeminiUnavailable("Gemini Live returned no spoken response. Try again or type your request.")
        self.geminiCompleted.emit(transcript or "Voice message", answer, audio)
        if audio:
            import numpy as np
            import sounddevice as sd
            sd.play(np.frombuffer(audio, dtype=np.int16), samplerate=24000)
            sd.wait()

class DocumentSummaryWorker(QObject):
    """Reads a user-chosen text file and summarises it off the interface thread.

    Runs on a daemon Python thread (not a QThread) on purpose: if the user closes NEXUS while a
    summary is still being written, the thread can be abandoned safely. Killing a thread that is
    running Python code is never safe, and a QThread must not be destroyed while it runs.
    """

    done = Signal(str, str, str)       # file name, summary text, which engine produced it
    failed = Signal(str, bool)         # message, True if it is a problem with the file (not the AI)

    def __init__(self, ai_service, path, parent=None):
        super().__init__(parent)
        self.ai = ai_service
        self.path = path
        self._thread = None
        self._abandoned = False

    # -- QThread-like surface used by the window ------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, name="NEXUS-Summary", daemon=True)
        self._thread.start()

    def isRunning(self):
        return self._thread is not None and self._thread.is_alive()

    def wait(self, msecs=30000):
        if self._thread is not None:
            self._thread.join(timeout=msecs / 1000.0)
        return not self.isRunning()

    def abandon(self):
        """The window is closing: finish quietly without signalling anything."""
        self._abandoned = True

    # -- worker thread -------------------------------------------------------------
    def _emit(self, signal, *args):
        if not self._abandoned:
            signal.emit(*args)

    def _run(self):
        from core.documents import DocumentError, read_document
        from core.gemini_engine import redact_secrets

        try:
            document = read_document(self.path)
        except DocumentError as error:
            self._emit(self.failed, str(error), True)
            return
        try:
            summary, where = self.ai.summarize_document(
                document.name, document.text, document.truncated, document.total_chars
            )
            if not summary:
                raise RuntimeError("The model returned an empty summary.")
            if document.truncated:
                summary += (f"\n\n_Only the first {len(document.text):,} of {document.total_chars:,} "
                            "characters were summarised._")
            self._emit(self.done, document.name, redact_secrets(summary), where)
        except Exception as error:  # noqa: BLE001 - shown to the user as a failed request
            self._emit(self.failed, redact_secrets(f"I could not summarise {document.name}: {error}"), False)

class _SystemCheckBridge(QObject):
    """Carries startup-check results from a worker thread to the UI thread."""

    finished = Signal(list, str)


class _TelemetryBridge(QObject):
    """Carries telemetry gathered on a worker thread back to the UI thread."""

    ready = Signal(object)
    static_ready = Signal(object)


# ============================================================
# MAIN WINDOW
# ============================================================


class MainWindow(QMainWindow):

    PAGES = ("home", "chat", "reminders", "memory", "system", "activity", "settings")
    PAGE_ALIASES = {"dashboard": "home", "assistant": "chat", "conversations": "chat", "customize": "settings"}

    def __init__(self):

        super().__init__()

        self.setWindowTitle("NEXUS")
        self.setMinimumSize(760, 560)

        self.settings = NEXUSSettings()
        self.window_settings = open_qsettings("NEXUS", "NEXUS")
        self._accent_color = QColor(str(self.window_settings.value("ui_accent", DEFAULT_ACCENT)))
        if not self._accent_color.isValid():
            self._accent_color = QColor(DEFAULT_ACCENT)
        self._theme_mode = str(self.settings.get("ui_theme", "dark") or "dark")
        theme().apply(QApplication.instance(), mode=self._theme_mode, accent=self._accent_color.name())

        stored_geometry = self.window_settings.value("windowGeometry")
        restored = False
        if stored_geometry is not None:
            try:
                restored = self.restoreGeometry(stored_geometry)
            except Exception:
                restored = False

        # Fit the window to the usable desktop on first launch, and keep a saved
        # geometry from ever exceeding the display after resolution or scaling changes.
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            max_width = max(760, available.width() - 24)
            max_height = max(560, available.height() - 24)
            if not restored:
                self.resize(min(1380, max_width), min(880, max_height))
            elif self.width() > max_width or self.height() > max_height:
                self.resize(max_width, max_height)
        elif not restored:
            self.resize(1380, 880)

        # ----------------------------------------------------
        # SYSTEM VALUES
        # ----------------------------------------------------

        self.cpu_value = None
        self.memory_value = None
        self.storage_value = None
        self.battery_value = None

        self.cpu_history = []
        self.memory_history = []
        self.disk_history = []
        self.network_history = []
        self.max_graph_points = 40

        # ----------------------------------------------------
        # CORE SERVICES
        # ----------------------------------------------------

        self.command_engine = CommandEngine()
        self.conversation_manager = ConversationManager()

        # ----------------------------------------------------
        # CONVERSATION STATE
        # ----------------------------------------------------

        self.current_conversation_id = None
        self.activity_events = []

        self.ai_threads = {}
        self.ai_workers = {}

        self.voice_enabled = False
        self.voice_output_active = False
        self.voice_output_interrupted = False
        self.current_voice_language = "auto"
        self.pending_voice_language = "auto"
        self.ai_voice_languages = {}
        self.kokoro_speech_queue = None
        self.kokoro_streamed_conversations = set()
        self._kokoro_unavailable_notified = False

        self._started_at = __import__("datetime").datetime.now()
        self.ai_request_count = 0
        self.pending_ai_requests = 0
        self.ai_success_count = 0
        self.response_times = []
        self.response_started_at = {}
        self._thinking_active = False
        self.streaming_ai_responses = {}

        self.voice_speech_thread = None
        self.voice_speech_worker = None

        self.shell_thread = None
        self.shell_worker = None
        self.shell_conversation_id = None
        self.shell_response_language = "auto"
        self.shell_command = ""

        # ----------------------------------------------------
        # THINKING INDICATOR
        # ----------------------------------------------------

        self.thinking_timer = QTimer(self)
        self.thinking_timer.timeout.connect(self.update_thinking_indicator)
        self.thinking_index = 0
        self.thinking_command = ""

        # ----------------------------------------------------
        # REAL HARDWARE TELEMETRY
        # ----------------------------------------------------

        self._network_sample = None
        self._network_download_mbps = 0.0
        self._network_upload_mbps = 0.0
        self._system_static_info = None
        self._system_log_entries = []
        self._last_system_log = 0.0
        self._last_battery_log = None
        self._telemetry_busy = False
        self._telemetry_thread = None
        self._static_thread = None
        self._telemetry_bridge = _TelemetryBridge(self)
        self._telemetry_bridge.ready.connect(self._apply_telemetry)
        self._telemetry_bridge.static_ready.connect(lambda _info: self._apply_static_system_info())

        # ----------------------------------------------------
        # BUILD UI
        # ----------------------------------------------------

        self.nav_buttons = {}
        self._current_page = None
        self._sidebar_pref_collapsed = self.window_settings.value("sidebar_collapsed", False, type=bool)
        self._sidebar_collapsed = None
        self._data_refresh_timer = QTimer(self)
        self._data_refresh_timer.setSingleShot(True)
        self._data_refresh_timer.timeout.connect(self._refresh_data_views)

        self.setup_ui()

        self.apply_runtime_settings(nexus_settings.load_user_settings(), announce=False)

        self.system_check_overlay = None
        self.system_fix_process = None

        self.refresh_conversation_list()

        self.restore_latest_conversation()

        # ----------------------------------------------------
        # SYSTEM MONITOR (sampled on a worker thread)
        # ----------------------------------------------------

        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.update_system_stats)
        self.monitor_timer.start(2000)
        self.update_system_stats()

        QTimer.singleShot(0, self.start_system_check)

        self.init_assistant_services()

    # ========================================================
    # NEXUS GLOBAL ACTIVATION
    # ========================================================

    def activate_nexus(self):
        """Bring the NEXUS window forward with a subtle desktop-style reveal."""
        try:
            if self.isMinimized():
                self.showNormal()
            elif not self.isVisible():
                self.show()

            self.raise_()
            self.activateWindow()

            if hasattr(self, "dashboard_input"):
                self.dashboard_input.setFocus()
        except Exception:
            pass

    def set_background_voice(self, service):
        """Attach the process-wide background voice service."""
        self.background_voice = service

    def closeEvent(self, event):
        try:
            self.window_settings.setValue("windowGeometry", self.saveGeometry())
        except Exception:  # noqa: BLE001
            pass
        tray = getattr(self, "tray", None)
        if self.settings.close_to_tray and tray is not None and tray.isVisible() and not getattr(self, "_quitting", False):
            # Keep reminders and the voice listener alive in the tray.
            event.ignore()
            self.hide()
            if not self.window_settings.value("tray_hint_shown", False, type=bool):
                self.window_settings.setValue("tray_hint_shown", True)
                tray.showMessage("NEXUS is still running", "NEXUS keeps running in the system tray so reminders can notify you. "
                                 "Right-click the tray icon and choose Exit to quit.")
            return
        self._quitting = True
        event.accept()
        QApplication.quit()

    def set_tray(self, tray):
        self.tray = tray

    def request_quit(self):
        self._quitting = True
        QApplication.quit()

    def shutdown(self):
        """Stop timers, workers and audio before the process exits."""
        self._quitting = True
        for name in ("reminder_scheduler",):
            service = getattr(self, name, None)
            if service is not None:
                try:
                    service.stop()
                except Exception:  # noqa: BLE001
                    pass
        for name in ("monitor_timer", "speech_watch_timer", "thinking_timer", "global_clock_timer",
                     "home_refresh_timer"):
            timer = getattr(self, name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:  # noqa: BLE001
                    pass
        if self.kokoro_speech_queue is not None:
            try:
                self.kokoro_speech_queue.close()
            except Exception:  # noqa: BLE001
                pass
        for thread in list(self.ai_threads.values()):
            try:
                thread.quit()
                thread.wait(1500)
            except Exception:  # noqa: BLE001
                pass
        for name, timeout in (("_system_check_thread", 4.0), ("_telemetry_thread", 2.0), ("_static_thread", 4.0)):
            worker_thread = getattr(self, name, None)
            if worker_thread is not None and worker_thread.is_alive():
                worker_thread.join(timeout=timeout)
        # Stop an active microphone capture and any running document summary, so closing the
        # window never leaves the microphone open or a thread running into interpreter exit.
        voice_worker = getattr(self, "voice_worker", None)
        if voice_worker is not None:
            try:
                if voice_worker.isRunning():
                    voice_worker.cancel()
                    voice_worker.wait(2000)
            except Exception:  # noqa: BLE001
                pass
        document_worker = getattr(self, "document_worker", None)
        if document_worker is not None:
            try:
                document_worker.abandon()   # a daemon thread: it is left to finish quietly, never killed
                document_worker.wait(1500)
            except Exception:  # noqa: BLE001
                pass

    # ========================================================
    # ASSISTANT SERVICES: reminders, greeting, data window
    # ========================================================

    def init_assistant_services(self):
        from core.reminders import ReminderScheduler

        self.tray = getattr(self, "tray", None)
        self.reminder_scheduler = ReminderScheduler(self.command_engine.assistant.reminders, parent=self)
        self.reminder_scheduler.reminder_due.connect(self.handle_reminder_due)
        # Start after the window exists so reminders missed while NEXUS was closed
        # are announced once the UI is ready.
        QTimer.singleShot(1500, self.reminder_scheduler.start)

        self.speech_watch_timer = QTimer(self)
        self.speech_watch_timer.setInterval(500)
        self.speech_watch_timer.timeout.connect(self._poll_speech)
        self.speech_watch_timer.start()

        if self.settings.startup_greeting:
            QTimer.singleShot(2500, self.show_startup_greeting)

    def show_startup_greeting(self):
        from core.assistant import build_greeting

        name = str(self.settings.get("user_name", "") or "")
        greeting = build_greeting(name)
        self.add_activity(greeting)
        try:
            conversation_id = self.ensure_conversation()
            self.conversation_manager.add_message(conversation_id, "assistant", greeting)
            self.render_current_conversation()
        except Exception:  # noqa: BLE001
            pass
        self.speak_response(greeting, self.current_voice_language)

    def handle_reminder_due(self, reminder, missed):
        """A reminder came due: notify, record it, and (optionally) speak it."""
        text = f"Reminder: {reminder.get('message', '')}"
        if missed:
            text += f" (this was due at {str(reminder.get('due_at', ''))[11:16]} - NEXUS wasn't running or the PC was asleep)"
        self.add_activity(text)
        try:
            conversation_id = self.ensure_conversation()
            self.conversation_manager.add_message(conversation_id, "assistant", f"⏰ {text}")
            self.render_current_conversation()
        except Exception:  # noqa: BLE001
            pass
        self.show_toast(text, "info", 6000)
        self._schedule_data_refresh()
        if self.settings.reminder_notifications:
            tray = getattr(self, "tray", None)
            if tray is not None and tray.isVisible():
                tray.showMessage("NEXUS reminder", text)
            if not self.isVisible():
                self.activate_nexus()
        if self.settings.speak_reminders and self.voice_enabled:
            self.speak_response(text, self.current_voice_language)

    def open_data_dialog(self):
        from ui.data_dialog import DataDialog

        dialog = DataDialog(self.command_engine.assistant, self.settings, self)
        dialog.exec()
        self.refresh_conversation_list()
        self._refresh_data_views()

    # ========================================================
    # MAIN UI
    # ========================================================

    def setup_ui(self):
        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        self.create_sidebar()
        root_layout.addWidget(self.sidebar)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("pageStack")
        root_layout.addWidget(self.page_stack, 1)

        self.dashboard_page = self.create_home_page()
        self.assistant_page = self.create_chat_page()
        self.reminders_page = RemindersPage(self.command_engine.assistant.reminders)
        self.reminders_page.toast.connect(self.show_toast)
        self.reminders_page.changed.connect(self._schedule_data_refresh)
        self.memory_page = MemoryPage(self.command_engine.assistant.memory, self.settings)
        self.memory_page.toast.connect(self.show_toast)
        self.system_page = self.create_system_page()
        self.activity_page = ActivityPage()
        self.activity_page.clearRequested.connect(self.clear_activity)
        self.settings_page = SettingsPage(self.settings, self)
        self.settings_page.settingsSaved.connect(self.apply_runtime_settings)
        self.settings_page.resetRequested.connect(self.apply_reset_preferences)
        self.settings_page.manageDataRequested.connect(self.open_data_dialog)
        self.settings_page.insert_section(self.create_appearance_section(), 0)
        settings_wrapper = QWidget()
        settings_layout = QVBoxLayout(settings_wrapper)
        settings_layout.setContentsMargins(36, 28, 36, 20)
        settings_layout.setSpacing(16)
        settings_layout.addWidget(PageHeader("Settings", "Appearance, AI engine, voice, privacy and how NEXUS runs on this PC."))
        settings_layout.addWidget(self.settings_page, 1)

        self.pages = {}
        for name, widget in (
            ("home", self.dashboard_page),
            ("chat", self.assistant_page),
            ("reminders", self.reminders_page),
            ("memory", self.memory_page),
            ("system", self.system_page),
            ("activity", self.activity_page),
            ("settings", settings_wrapper),
        ):
            self.pages[name] = widget
            self.page_stack.addWidget(widget)

        self.toast = Toast(root)

        self.global_clock_timer = QTimer(self)
        self.global_clock_timer.timeout.connect(self.update_dashboard_clock)
        self.global_clock_timer.start(1000)
        self.update_dashboard_clock()

        # Relative times ("in 5 minutes", "Yesterday") on the home screen stay current.
        self.home_refresh_timer = QTimer(self)
        self.home_refresh_timer.timeout.connect(self._schedule_data_refresh)
        self.home_refresh_timer.start(30000)

        self._install_shortcuts()
        self._apply_sidebar_mode()
        self.switch_page("home")

    def _install_shortcuts(self):
        bindings = [
            ("Ctrl+N", self.start_new_conversation),
            ("Ctrl+M", self.capture_voice_command),
            ("Ctrl+K", self.focus_conversation_search),
            ("Ctrl+B", self.toggle_sidebar),
            ("Ctrl+,", lambda: self.switch_page("settings")),
            ("Ctrl+Shift+L", self.toggle_theme),
            ("Esc", self._escape_pressed),
        ]
        for index, name in enumerate(self.PAGES[:-1], start=1):
            bindings.append((f"Ctrl+{index}", lambda n=name: self.switch_page(n)))
        self._shortcuts = []
        for keys, handler in bindings:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def _escape_pressed(self):
        if self.interrupt_voice_output():
            return
        focused = QApplication.focusWidget()
        if isinstance(focused, TerminalInput):
            focused.clear()

    # ========================================================
    # APPEARANCE
    # ========================================================

    def create_appearance_section(self):
        card = QFrame()
        card.setObjectName("dashboardPanel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("Appearance & you")
        title.setObjectName("cardTitle")
        layout.addWidget(title)
        subtitle = QLabel("Changes apply immediately.")
        subtitle.setObjectName("mutedText")
        layout.addWidget(subtitle)

        self.theme_selector = Segmented((("dark", "Dark"), ("light", "Light"), ("system", "Match Windows")))
        self.theme_selector.set_value(self._theme_mode)
        self.theme_selector.changed.connect(self.set_theme_mode)
        layout.addWidget(SettingsPage._row("Theme", self.theme_selector))

        swatch_row = QWidget()
        swatches = QHBoxLayout(swatch_row)
        swatches.setContentsMargins(0, 0, 0, 0)
        swatches.setSpacing(8)
        self.accent_swatches = {}
        for name, color in ACCENT_PRESETS:
            button = QPushButton()
            button.setObjectName("swatch")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(name)
            button.setAccessibleName(f"{name} accent colour")
            button.setStyleSheet(f"QPushButton#swatch {{ background: {color}; }}")
            button.clicked.connect(lambda _=False, c=color: self.apply_accent_color(c))
            swatches.addWidget(button)
            self.accent_swatches[color.lower()] = button
        custom = QPushButton("Custom…")
        custom.setObjectName("ghostButton")
        custom.setCursor(Qt.PointingHandCursor)
        custom.clicked.connect(self._choose_custom_accent)
        swatches.addWidget(custom)
        layout.addWidget(SettingsPage._row("Accent colour", swatch_row))
        self._sync_accent_swatches()

        self.user_name_input = QLineEdit(str(self.settings.get("user_name", "") or ""))
        self.user_name_input.setMaxLength(50)
        self.user_name_input.setPlaceholderText("Optional")
        self.user_name_input.setMinimumWidth(220)
        self.user_name_input.editingFinished.connect(self._save_user_name)
        layout.addWidget(SettingsPage._row("Your name", self.user_name_input,
                                           "Used in greetings. Leave blank for a neutral greeting."))
        return card

    def _save_user_name(self):
        name = self.user_name_input.text().strip()
        if name == str(self.settings.get("user_name", "") or ""):
            return
        self.settings.set("user_name", name)
        self.update_dashboard_greeting(name)
        self.show_toast("Name saved." if name else "Name cleared.")

    def _choose_custom_accent(self):
        chosen = QColorDialog.getColor(self._accent_color, self, "Choose an accent colour")
        if chosen.isValid():
            self.apply_accent_color(chosen)

    def _sync_accent_swatches(self):
        current = self._accent_color.name().lower()
        for color, button in getattr(self, "accent_swatches", {}).items():
            button.setChecked(color == current)

    def apply_accent_color(self, color):
        accent = QColor(color)
        if not accent.isValid():
            return
        self._accent_color = accent
        theme().apply(QApplication.instance(), accent=accent.name())
        self._sync_accent_swatches()
        if hasattr(self, "settings"):
            self.settings.set("ui_accent", accent.name())

    def set_theme_mode(self, mode):
        self._theme_mode = mode if mode in ("dark", "light", "system") else "dark"
        self.settings.set("ui_theme", self._theme_mode)
        # Restyling every widget takes a moment on slower PCs; show that it is working.
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            theme().apply(QApplication.instance(), mode=self._theme_mode)
        finally:
            QApplication.restoreOverrideCursor()
        if hasattr(self, "theme_selector"):
            self.theme_selector.set_value(self._theme_mode)
        self._refresh_theme_button()

    def toggle_theme(self):
        self.set_theme_mode("light" if theme().resolved_mode() == "dark" else "dark")

    def _refresh_theme_button(self, *_):
        button = getattr(self, "theme_button", None)
        if button is None:
            return
        dark = theme().resolved_mode() == "dark"
        button.set_kind("sun" if dark else "moon")
        tip = "Switch to light theme (Ctrl+Shift+L)" if dark else "Switch to dark theme (Ctrl+Shift+L)"
        button.setToolTip(tip)
        button.setAccessibleName(tip)

    def open_customize_dialog(self):
        """Appearance now lives at the top of Settings."""
        self.switch_page("settings")

    def update_dashboard_greeting(self, display_name=None):
        if not hasattr(self, "dashboard_greeting_label"):
            return
        if display_name is None:
            display_name = str(self.settings.get("user_name", "") or "").strip()
        from datetime import datetime

        hour = datetime.now().hour
        part = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening"
        greeting = f"Good {part}, {display_name}" if display_name else f"Good {part}"
        self.dashboard_greeting_label.setText(greeting)

    def _sync_voice_language_controls(self, language):
        for combo in (
            getattr(self, "voice_language_combo", None),
            getattr(getattr(self, "settings_page", None), "voice_language", None),
        ):
            if combo is None:
                continue
            index = combo.findData(language)
            if index >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)

    def filter_conversations(self, query):
        query = str(query or "").strip().lower()
        if not hasattr(self, "conversation_list"):
            return
        for index in range(self.conversation_list.count()):
            item = self.conversation_list.item(index)
            cid = item.data(Qt.UserRole)
            match = True
            if query:
                title = str(item.data(Qt.UserRole + 1) or "").lower()
                message_text = ""
                try:
                    message_text = " ".join(
                        str(m.get("content", ""))
                        for m in self.conversation_manager.get_messages(cid)
                    ).lower()
                except Exception:
                    pass
                match = query in title or query in message_text
            item.setHidden(not match)

    def open_first_search_result(self):
        query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        if not query or not hasattr(self, "conversation_list"):
            return
        for index in range(self.conversation_list.count()):
            item = self.conversation_list.item(index)
            if not item.isHidden():
                self.load_conversation_from_item(item)
                return

    # ========================================================
    # IN-APP SYSTEM CHECK
    # ========================================================

    def start_system_check(self):
        self.system_check_overlay = SystemCheckDialog(parent=self.centralWidget())
        self.system_check_overlay.setGeometry(self.centralWidget().rect())
        self.system_check_overlay.raise_()
        self.system_check_overlay.continueRequested.connect(self.finish_system_check)
        self.system_check_overlay.retryRequested.connect(self._run_system_check)
        self.system_check_overlay.fixRequested.connect(self._attempt_system_fix)
        self.system_check_overlay.show()
        self.system_check_overlay.update_status("Running startup diagnostics…")
        QTimer.singleShot(80, self._run_system_check)

    def _run_system_check(self):
        """Run the checks on a worker thread (they make network calls); results return via a signal."""
        if self.system_check_overlay is None or getattr(self, "_system_check_running", False):
            return
        self._system_check_running = True
        self.system_check_overlay.update_status("Running startup diagnostics…")
        if not hasattr(self, "_system_check_bridge"):
            self._system_check_bridge = _SystemCheckBridge(self)
            self._system_check_bridge.finished.connect(self._system_check_done)

        def work():
            try:
                results, error = NEXUSSystemChecker().run_all_checks(), ""
            except Exception as failure:  # noqa: BLE001
                results, error = [], str(failure)
            if not getattr(self, "_quitting", False):  # never signal into a window that is closing
                self._system_check_bridge.finished.emit(results, error)

        # Kept so shutdown() can wait for it: a thread still importing modules or talking to
        # Qt while the interpreter finalises is what used to crash NEXUS right after launch.
        self._system_check_thread = threading.Thread(target=work, name="NEXUS-SystemCheck", daemon=True)
        self._system_check_thread.start()

    def _system_check_done(self, results, error):
        self._system_check_running = False
        if self.system_check_overlay is None:
            return
        self.system_check_overlay.set_results(results)
        if error:
            self.system_check_overlay.update_status(f"System check could not complete: {error}")
            return
        required_ok = bool(results) and all(
            bool(getattr(result, "success", False))
            for result in results
            if bool(getattr(result, "required", True))
        )
        if required_ok:
            # Nothing needs the user's attention: step aside on its own instead of
            # making them click "Continue" on every launch.
            self.system_check_overlay.update_status("All set. Starting NEXUS…")
            QTimer.singleShot(700, self.finish_system_check)

    def _attempt_system_fix(self, index):
        if self.system_check_overlay is None:
            return

        results = list(getattr(self.system_check_overlay, "results", []) or [])
        if index < 0 or index >= len(results):
            return

        result = results[index]
        text = f"{getattr(result, 'name', '')} {getattr(result, 'details', '')}".lower()

        try:
            if "nexus local model" in text or ("modelfile" in text and "customized" in text):
                self.system_check_overlay.set_busy(True)
                self.system_check_overlay.update_status("NEXUS is creating the customized local model…")
                modelfile = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "Modelfile")
                self._new_fix_process(self._system_fix_finished).start("ollama", ["create", "nexus", "-f", modelfile])
                return

            if "ollama" in text and "llama3.1:8b" in text and "model" in text:
                self.system_check_overlay.set_busy(True)
                self.system_check_overlay.update_status("NEXUS is preparing the local AI model…")
                self._new_fix_process(self._system_fix_finished).start("ollama", ["pull", "llama3.1:8b"])
                return

            if "ollama" in text:
                self.system_check_overlay.set_busy(True)
                self.system_check_overlay.update_status("NEXUS is starting the local AI service…")
                self._new_fix_process().start("ollama", ["serve"])
                QTimer.singleShot(2500, self._system_fix_service_check)
                return

            if "microphone" in text or "microphone" in getattr(result, "name", "").lower():
                try:
                    os.startfile("ms-settings:privacy-microphone")
                    self.system_check_overlay.update_status(
                        "Microphone settings opened. Enable microphone access, then run the check again."
                    )
                except Exception as error:
                    self.system_check_overlay.update_status(
                        f"Open Windows microphone settings and enable access, then run the check again. ({error})"
                    )
                return

            self.system_check_overlay.update_status(
                "Please complete this requirement on the PC, then run the check again."
            )
        except Exception as error:
            self.system_check_overlay.set_busy(False)
            self.system_check_overlay.update_status(f"Automatic fix could not be started: {error}")

    def _system_fix_finished(self, exit_code, exit_status):
        self.system_fix_process = None
        if self.system_check_overlay is not None:
            self.system_check_overlay.set_busy(False)
            self.system_check_overlay.update_status("Rechecking system requirements…")
        QTimer.singleShot(250, self._run_system_check)

    def _system_fix_failed(self, error):
        """The helper program could not even be started (for example Ollama is not installed)."""
        self.system_fix_process = None
        if self.system_check_overlay is not None:
            self.system_check_overlay.set_busy(False)
            self.system_check_overlay.update_status(
                "NEXUS could not start 'ollama'. Install Ollama from https://ollama.com/download, "
                "then choose Retry - or switch to Online AI in Settings."
            )

    def _new_fix_process(self, finished=None):
        process = QProcess(self)
        if finished is not None:
            process.finished.connect(finished)
        process.errorOccurred.connect(
            lambda error, p=process: self._system_fix_failed(error)
            if error == QProcess.ProcessError.FailedToStart else None
        )
        self.system_fix_process = process
        return process

    def _system_fix_service_check(self):
        if self.system_check_overlay is not None:
            self.system_check_overlay.set_busy(False)
            self.system_check_overlay.update_status("Rechecking system requirements…")
        QTimer.singleShot(250, self._run_system_check)

    def finish_system_check(self):
        if self.system_check_overlay is None:
            return

        # Missing components never lock the user out of the app; the dialog has
        # already told them what is missing and Settings can fix it later.
        self.system_check_overlay.hide()
        self.system_check_overlay.deleteLater()
        self.system_check_overlay = None
        if self._current_page in (None, "home"):
            self.switch_page("home")
        if hasattr(self, "dashboard_input") and self._current_page == "home":
            self.dashboard_input.setFocus()

    # ========================================================
    # SIDEBAR
    # ========================================================

    def create_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(4)

        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 0)
        brand.setSpacing(10)
        self.brand_mark = OrbMark(26)
        self.brand_mark.setToolTip("NEXUS")
        brand.addWidget(self.brand_mark)
        self.brand_text = QWidget()
        brand_text = QVBoxLayout(self.brand_text)
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand_text.setSpacing(0)
        wordmark = QLabel("NEXUS")
        wordmark.setObjectName("brandWordmark")
        brand_text.addWidget(wordmark)
        tagline = QLabel("Personal AI assistant")
        tagline.setObjectName("brandTagline")
        brand_text.addWidget(tagline)
        brand.addWidget(self.brand_text, 1)
        self.collapse_button = IconButton("sidebar", "Collapse sidebar (Ctrl+B)", size=30, icon_size=17)
        self.collapse_button.clicked.connect(self.toggle_sidebar)
        brand.addWidget(self.collapse_button)
        layout.addLayout(brand)
        layout.addSpacing(14)

        self.new_conversation_button = QPushButton("  New chat")
        self.new_conversation_button.setObjectName("newChatButton")
        self.new_conversation_button.setCursor(Qt.PointingHandCursor)
        self.new_conversation_button.setToolTip("Start a new conversation (Ctrl+N)")
        self.new_conversation_button.setMinimumHeight(38)
        self.new_conversation_button.setIconSize(QSize(17, 17))
        self.new_conversation_button.clicked.connect(self.start_new_conversation)
        layout.addWidget(self.new_conversation_button)
        layout.addSpacing(10)

        for name, icon, label, hint in (
            ("home", "home", "Home", "Ctrl+1"),
            ("chat", "chat", "Chat", "Ctrl+2"),
            ("reminders", "bell", "Reminders", "Ctrl+3"),
            ("memory", "memory", "Memory", "Ctrl+4"),
            ("system", "system", "System", "Ctrl+5"),
            ("activity", "activity", "Activity", "Ctrl+6"),
        ):
            self.create_nav_button(name, icon, label, hint, layout)

        self.history_section = QWidget()
        history = QVBoxLayout(self.history_section)
        history.setContentsMargins(0, 14, 0, 0)
        history.setSpacing(6)
        history_label = QLabel("RECENT CHATS")
        history_label.setObjectName("sectionLabel")
        history_label.setContentsMargins(8, 0, 0, 0)
        history.addWidget(history_label)

        search_holder = QWidget()
        search_layout = QHBoxLayout(search_holder)
        search_layout.setContentsMargins(0, 0, 0, 0)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search chats  (Ctrl+K)")
        self.search_input.setAccessibleName("Search conversations")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.filter_conversations)
        self.search_input.returnPressed.connect(self.open_first_search_result)
        search_layout.addWidget(self.search_input)
        search_icon = IconLabel("search", 15, "faint", self.search_input)
        search_icon.move(10, 9)
        history.addWidget(search_holder)

        self.conversation_list = QListWidget()
        self.conversation_list.setObjectName("conversationList")
        self.conversation_list.setUniformItemSizes(True)
        self.conversation_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.conversation_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.conversation_list.customContextMenuRequested.connect(self.show_conversation_context_menu)
        self.conversation_list.itemClicked.connect(self.load_conversation_from_item)
        self.conversation_list.itemActivated.connect(self.load_conversation_from_item)
        self.conversation_list.setAccessibleName("Conversation history")
        history.addWidget(self.conversation_list, 1)
        self.history_empty = QLabel("Your conversations will appear here.")
        self.history_empty.setObjectName("faintText")
        self.history_empty.setWordWrap(True)
        self.history_empty.setContentsMargins(8, 4, 8, 4)
        history.addWidget(self.history_empty)
        self.history_empty_spacer = QWidget()
        self.history_empty_spacer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        history.addWidget(self.history_empty_spacer, 1)
        layout.addWidget(self.history_section, 1)
        self.history_spacer = QWidget()
        self.history_spacer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout.addWidget(self.history_spacer, 1)

        divider = QFrame()
        divider.setObjectName("divider")
        layout.addWidget(divider)
        layout.addSpacing(4)
        self.create_nav_button("settings", "settings", "Settings", "Ctrl+,", layout)

        footer = QHBoxLayout()
        footer.setContentsMargins(4, 4, 0, 0)
        footer.setSpacing(6)
        self.theme_button = IconButton("sun", "Switch theme", size=30, icon_size=16)
        self.theme_button.clicked.connect(self.toggle_theme)
        footer.addWidget(self.theme_button)
        self.engine_status_label = ElidedLabel()
        self.engine_status_label.setObjectName("faintText")
        footer.addWidget(self.engine_status_label, 1)
        layout.addLayout(footer)
        theme().changed.connect(self._refresh_theme_button)
        theme().changed.connect(self._refresh_sidebar_icons)
        self._refresh_theme_button()
        self._refresh_sidebar_icons()

    def _refresh_sidebar_icons(self, *_):
        palette = current_palette()
        self.new_conversation_button.setIcon(make_icon("plus", palette.on_accent, 17, stroke=2.0))

    def create_conversation_row(self, title, stamp):
        """One history row: the title (elided) and when it was last used."""
        widget = QWidget()
        widget.setObjectName("conversationRow")
        widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)
        title_label = ElidedLabel(str(title or "New conversation"))
        title_label.setObjectName("conversationRowTitle")
        layout.addWidget(title_label, 1)
        stamp_label = QLabel(str(stamp or ""))
        stamp_label.setObjectName("conversationRowStamp")
        layout.addWidget(stamp_label)
        return widget

    def create_nav_button(self, page_name, icon_kind, label_text, hint="", layout=None):
        button = NavButton(icon_kind, label_text, hint)
        button.clicked.connect(lambda checked=False, name=page_name: self.switch_page(name))
        self.nav_buttons[page_name] = button
        (layout or self.sidebar.layout()).addWidget(button)
        return button

    def toggle_sidebar(self):
        self._sidebar_pref_collapsed = not bool(self._sidebar_collapsed)
        self.window_settings.setValue("sidebar_collapsed", self._sidebar_pref_collapsed)
        self._apply_sidebar_mode()

    def _apply_sidebar_mode(self):
        collapsed = bool(self._sidebar_pref_collapsed or self.width() < 980)
        if collapsed == self._sidebar_collapsed:
            return
        self._sidebar_collapsed = collapsed
        self.sidebar.setFixedWidth(68 if collapsed else 264)
        self.brand_text.setVisible(not collapsed)
        self.history_section.setVisible(not collapsed)
        self.history_spacer.setVisible(collapsed)
        self.engine_status_label.setVisible(not collapsed)
        self.new_conversation_button.setText("" if collapsed else "  New chat")
        for button in self.nav_buttons.values():
            button.set_collapsed(collapsed)
        self.collapse_button.set_kind("sidebar")
        tip = "Expand sidebar (Ctrl+B)" if collapsed else "Collapse sidebar (Ctrl+B)"
        self.collapse_button.setToolTip(tip)
        self.collapse_button.setAccessibleName(tip)
        layout = self.sidebar.layout()
        layout.setContentsMargins(10 if collapsed else 12, 16, 10 if collapsed else 12, 12)

    def focus_conversation_search(self):
        if self._sidebar_collapsed:
            self._sidebar_pref_collapsed = False
            self._apply_sidebar_mode()
        if self.search_input.isVisible():
            self.search_input.setFocus()
            self.search_input.selectAll()

    # ========================================================
    # PAGE SWITCHING
    # ========================================================

    def switch_page(self, page_name):
        requested = str(page_name or "home")
        name = self.PAGE_ALIASES.get(requested, requested)
        page = getattr(self, "pages", {}).get(name)
        if page is None:
            return
        changed = name != self._current_page
        self._current_page = name
        self.page_stack.setCurrentWidget(page)
        for key, button in self.nav_buttons.items():
            button.setChecked(key == name)
        if changed:
            fade_in(page)
        if name == "chat":
            self.render_current_conversation()
            if requested == "conversations":
                self.focus_conversation_search()
            else:
                self.assistant_input.setFocus()
        elif name == "home":
            self.update_dashboard_greeting()
            self.refresh_home_cards()
        elif name == "reminders":
            self.reminders_page.refresh()
        elif name == "memory":
            self.memory_page.refresh()
        elif name == "system":
            self._ensure_static_system_info()

    # ========================================================
    # HOME
    # ========================================================

    def create_home_page(self):
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(40, 30, 40, 36)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(12)
        greeting_box = QVBoxLayout()
        greeting_box.setSpacing(2)
        self.dashboard_greeting_label = QLabel("Good evening")
        self.dashboard_greeting_label.setObjectName("heroGreeting")
        self.dashboard_greeting_label.setTextFormat(Qt.PlainText)
        greeting_box.addWidget(self.dashboard_greeting_label)
        self.dashboard_date = QLabel()
        self.dashboard_date.setObjectName("heroSubtitle")
        greeting_box.addWidget(self.dashboard_date)
        top.addLayout(greeting_box, 1)
        self.home_status = StatusPill()
        top.addWidget(self.home_status, 0, Qt.AlignTop)
        self.dashboard_engine_label = QLabel()
        self.dashboard_engine_label.setObjectName("badge")
        top.addWidget(self.dashboard_engine_label, 0, Qt.AlignTop)
        root.addLayout(top)
        # Kept for the clock code: the time is part of the date line on Home.
        self.dashboard_clock = QLabel()
        self.dashboard_clock.hide()

        hero = QVBoxLayout()
        hero.setContentsMargins(0, 18, 0, 0)
        hero.setSpacing(6)
        self.dashboard_core_widget = NexusOrb(240)
        self.dashboard_core_widget.setFixedSize(240, 240)
        self.dashboard_core_widget.clicked.connect(self._orb_clicked)
        hero.addWidget(self.dashboard_core_widget, 0, Qt.AlignHCenter)
        self.orb_state_label = QLabel()
        self.orb_state_label.setObjectName("orbState")
        self.orb_state_label.setAlignment(Qt.AlignCenter)
        hero.addWidget(self.orb_state_label)
        self.orb_caption_label = QLabel()
        self.orb_caption_label.setObjectName("orbCaption")
        self.orb_caption_label.setAlignment(Qt.AlignCenter)
        self.orb_caption_label.setWordWrap(True)
        hero.addWidget(self.orb_caption_label)
        hero.addSpacing(16)

        self.home_composer = Composer("Ask NEXUS anything…", show_language=False)
        self.home_composer.setMaximumWidth(740)
        self.dashboard_input = self.home_composer.input
        self.dashboard_input.setObjectName("composerInput")
        self.dashboard_input.sendRequested.connect(self.handle_dashboard_command)
        self.dashboard_input.newConversationRequested.connect(self.start_new_conversation)
        self.mic_button = self.home_composer.mic_button
        self.mic_button.clicked.connect(self.capture_voice_command)
        self.voice_toggle = self.home_composer.voice_toggle
        self.voice_toggle.toggled.connect(self.set_voice_mode)
        self.dashboard_attach_button = self.home_composer.attach_button
        self.dashboard_attach_button.clicked.connect(self.attach_dashboard_file)
        self.home_composer.remove_attachment_button.clicked.connect(self.clear_dashboard_attachment)
        self.dashboard_attachment = None
        hero.addLayout(self._centered(self.home_composer))

        chips_holder = QWidget()
        chips_holder.setMaximumWidth(760)
        chips = FlowLayout(chips_holder, spacing=8)
        for label, prompt in SUGGESTIONS:
            chip = QPushButton(label)
            chip.setObjectName("chip")
            chip.setCursor(Qt.PointingHandCursor)
            chip.setToolTip(f"Ask NEXUS: “{prompt}”")
            chip.clicked.connect(lambda _=False, text=prompt: self.handle_dashboard_command(text))
            chips.addWidget(chip)
        hero.addSpacing(6)
        hero.addLayout(self._centered(chips_holder))
        root.addLayout(hero)

        root.addSpacing(30)
        glance = QLabel("AT A GLANCE")
        glance.setObjectName("sectionLabel")
        root.addWidget(glance)
        root.addSpacing(10)

        grid = ResponsiveGrid(min_column_width=340, max_columns=2, spacing=16)

        self.home_reminders_card = Card("Up next", icon="bell", action_text="All reminders",
                                        action=lambda: self.switch_page("reminders"))
        self.home_reminders_layout = QVBoxLayout()
        self.home_reminders_layout.setSpacing(2)
        self.home_reminders_card.body.addLayout(self.home_reminders_layout)
        self.home_reminders_card.body.addStretch(1)
        grid.add(self.home_reminders_card)

        self.home_chats_card = Card("Recent chats", icon="chat", action_text="Open chat",
                                    action=lambda: self.switch_page("chat"))
        self.home_chats_layout = QVBoxLayout()
        self.home_chats_layout.setSpacing(2)
        self.home_chats_card.body.addLayout(self.home_chats_layout)
        self.home_chats_card.body.addStretch(1)
        grid.add(self.home_chats_card)

        pc_card = Card("This PC", icon="system", action_text="Details", action=lambda: self.switch_page("system"))
        self.dashboard_system_values = {}
        self.dashboard_system_bars = {}
        for key, title in (("cpu", "Processor"), ("memory", "Memory"), ("disk", "Storage"), ("battery", "Battery")):
            row = QHBoxLayout()
            row.setSpacing(10)
            label = QLabel(title)
            label.setObjectName("mutedText")
            label.setMinimumWidth(78)
            row.addWidget(label)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setAccessibleName(f"{title} usage")
            row.addWidget(bar, 1)
            value = QLabel("—")
            value.setObjectName("rowTitle")
            value.setMinimumWidth(44)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(value)
            pc_card.body.addLayout(row)
            self.dashboard_system_values[key] = value
            self.dashboard_system_bars[key] = bar
        pc_card.body.addStretch(1)
        grid.add(pc_card)

        self.home_activity_card = Card("Recent activity", icon="activity", action_text="View all",
                                       action=lambda: self.switch_page("activity"))
        self.dashboard_activity_layout = QVBoxLayout()
        self.dashboard_activity_layout.setSpacing(2)
        self.home_activity_card.body.addLayout(self.dashboard_activity_layout)
        self.home_activity_card.body.addStretch(1)
        grid.add(self.home_activity_card)

        root.addWidget(grid)
        root.addStretch(1)

        self._set_orb_text("sleeping")
        self.update_dashboard_greeting()
        return scroll_page(content)

    @staticmethod
    def _centered(widget):
        """Centre a widget that should grow up to its maximum width."""
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(widget, 100)
        row.addStretch(1)
        return row

    def _orb_clicked(self):
        if self.voice_output_active:
            self.interrupt_voice_output()
            return
        self.capture_voice_command()

    def _set_orb_text(self, state):
        title, caption = ORB_TEXT.get(state, ORB_TEXT["sleeping"])
        if state == "thinking" and self._thinking_active and self.thinking_command:
            preview = str(self.thinking_command).replace("\n", " ")
            preview = preview if len(preview) <= 70 else preview[:67] + "…"
            caption = f"Working on “{preview}”"
        if hasattr(self, "orb_state_label"):
            self.orb_state_label.setText(title)
            self.orb_caption_label.setText(caption)
        orb = getattr(self, "dashboard_core_widget", None)
        if orb is not None:
            orb.setAccessibleDescription(f"{title} {caption}")

    def refresh_dashboard_metrics(self):
        """Update the This PC card from real local measurements."""
        values = {
            "cpu": self.cpu_value,
            "memory": self.memory_value,
            "disk": self.storage_value,
        }
        battery = self.battery_value
        values["battery"] = None if battery is None else battery.get("percent")
        for key, value in values.items():
            label = getattr(self, "dashboard_system_values", {}).get(key)
            bar = getattr(self, "dashboard_system_bars", {}).get(key)
            available = value is not None
            if label is not None:
                label.setText("N/A" if not available else f"{float(value):.0f}%")
            if bar is not None:
                bar.setEnabled(available)
                number = 0 if not available else max(0, min(100, int(float(value))))
                bar.setValue(number)
                level = "ok"
                if key != "battery" and number >= 90:
                    level = "high"
                elif key != "battery" and number >= 75:
                    level = "warn"
                elif key == "battery" and available and number <= 15 and not battery.get("charging"):
                    level = "high"
                if bar.property("level") != level:
                    bar.setProperty("level", level)
                    repolish(bar)
                if key == "battery" and battery is not None:
                    state = "charging" if battery.get("charging") else "on battery"
                    bar.setToolTip(f"Battery {state}")

    def attach_dashboard_file(self):
        """Attach a small UTF-8 text/code file to the next explicit prompt."""
        allowed = "Text and source files (*.txt *.md *.py *.json *.csv *.log *.yaml *.yml *.toml *.xml *.html *.css *.js *.ts *.sql *.ini *.cfg *.ps1 *.bat *.sh)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Attach a text or code file",
            str(Path.home()),
            allowed,
        )
        if not file_path:
            return

        path = Path(file_path)
        try:
            if path.stat().st_size > 32 * 1024:
                raise ValueError("Choose a text or code file no larger than 32 KB.")
            content = path.read_bytes().decode("utf-8-sig")
            if "\x00" in content:
                raise ValueError("This looks like a binary file. Attach a UTF-8 text or code file instead.")
        except (OSError, UnicodeDecodeError, ValueError) as error:
            QMessageBox.warning(self, "Could not attach file", str(error))
            return

        self.dashboard_attachment = {"name": path.name, "content": content}
        for composer in (getattr(self, "home_composer", None), getattr(self, "chat_composer", None)):
            if composer is not None:
                composer.set_attachment(path.name)
                composer.attachment_chip.setToolTip(
                    "Attached to your next message only; processed by the AI engine selected in Settings."
                )
        self.add_activity(f"Text file attached for the next assistant request: {path.name}")

    def clear_dashboard_attachment(self):
        self.dashboard_attachment = None
        for composer in (getattr(self, "home_composer", None), getattr(self, "chat_composer", None)):
            if composer is not None:
                composer.set_attachment(None)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                # Hide now so the old row is not painted again; keep its parent so Qt (not
                # Python's garbage collector) deletes it, safely, from the event loop.
                widget.hide()
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _home_row(self, icon, role, title, meta, callback=None, tooltip=""):
        row = QPushButton() if callback else QFrame()
        row.setObjectName("homeRow" if callback else "listRow")
        if callback:
            row.setCursor(Qt.PointingHandCursor)
            row.clicked.connect(callback)
            row.setAccessibleName(title)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(10)
        layout.addWidget(IconLabel(icon, 16, role))
        label = ElidedLabel(title)
        label.setObjectName("rowTitle")
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(label, 1)
        if meta:
            meta_label = QLabel(meta)
            meta_label.setObjectName("rowMeta")
            meta_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            layout.addWidget(meta_label)
        if tooltip:
            row.setToolTip(tooltip)
        row.setMinimumHeight(36)
        return row

    def refresh_home_cards(self):
        self.refresh_dashboard_recent_conversations()
        self.refresh_dashboard_timeline()
        self.refresh_dashboard_activity_feed()

    def refresh_dashboard_timeline(self):
        """The "Up next" card: real pending reminders."""
        layout = getattr(self, "home_reminders_layout", None)
        if layout is None:
            return
        from datetime import datetime

        from core.timeparse import describe_due

        self._clear_layout(layout)
        reminders = self.reminders_page.upcoming(4) if hasattr(self, "reminders_page") else []
        now = datetime.now()
        if not reminders:
            layout.addWidget(EmptyState("bell", "Nothing scheduled", "Try “remind me to call Mum at 6pm”.",
                                        compact=True))
            return
        for reminder in reminders:
            overdue = reminder.due_at < now
            when = describe_due(reminder.due_at, now)
            layout.addWidget(self._home_row(
                "alert" if overdue else "clock", "danger" if overdue else "accent", reminder.message,
                ("Overdue · " if overdue else "") + when, lambda: self.switch_page("reminders"),
            ))
        self._update_reminder_badge()

    def _update_reminder_badge(self):
        button = self.nav_buttons.get("reminders")
        if button is None or not hasattr(self, "reminders_page"):
            return
        count = len(self.reminders_page.upcoming(99))
        button.setToolTip(f"Reminders — {count} upcoming  (Ctrl+3)" if count else "Reminders  (Ctrl+3)")

    def refresh_dashboard_recent_conversations(self):
        layout = getattr(self, "home_chats_layout", None)
        if layout is None:
            return
        self._clear_layout(layout)
        try:
            conversations = self.conversation_manager.get_conversations()[:4]
        except Exception:  # noqa: BLE001
            conversations = []
        if not conversations:
            layout.addWidget(EmptyState("chat", "No chats yet", "Ask NEXUS something above to get started.",
                                        compact=True))
            return
        for conversation in conversations:
            cid = conversation.get("id")
            layout.addWidget(self._home_row(
                "chat", "muted", str(conversation.get("title") or "New conversation"),
                friendly_time(conversation.get("updated_at") or conversation.get("created_at")),
                lambda _=False, c=cid: self.load_conversation(c),
            ))

    def refresh_dashboard_activity_feed(self):
        layout = getattr(self, "dashboard_activity_layout", None)
        if layout is None:
            return
        self._clear_layout(layout)
        events = list(reversed(self.activity_events[-4:]))
        if not events:
            layout.addWidget(EmptyState("activity", "All quiet", "What NEXUS does will show up here.", compact=True))
            return
        for stamp, text in events:
            icon, role = activity_icon(text)
            single_line = " ".join(str(text).split())
            layout.addWidget(self._home_row(icon, role, single_line, stamp[:5], tooltip=str(text)[:400]))

    def _schedule_data_refresh(self):
        if not getattr(self, "_quitting", False):
            self._data_refresh_timer.start(120)

    def _refresh_data_views(self):
        if getattr(self, "_quitting", False):
            return
        if self._current_page == "reminders":
            self.reminders_page.refresh()
        if self._current_page == "memory":
            self.memory_page.refresh()
        self.refresh_dashboard_timeline()
        self.refresh_dashboard_recent_conversations()

    def show_toast(self, text, kind="success", msecs=2600):
        toast = getattr(self, "toast", None)
        if toast is not None and not getattr(self, "_quitting", False):
            toast.show_message(str(text), kind, msecs)

    def _copy_text(self, text):
        QApplication.clipboard().setText(str(text or ""))
        self.show_toast("Copied to clipboard.")

    def read_aloud(self, text):
        """Speak one message on request, even when automatic spoken replies are off."""
        if not text:
            return
        if self.settings.legacy_openai_voice_enabled:
            self._speak_response_legacy_openai(text, self.current_voice_language)
            return
        manager = self._ensure_speech_manager()
        if manager.enqueue(text, self.current_voice_language or "auto"):
            self.voice_output_active = True
            self.set_core_state("speaking")
            self.assistant_status.setText("● SPEAKING")
        else:
            self.show_toast(f"Speech is unavailable: {manager.last_error or 'no speech engine found.'}", "error", 5000)

    def apply_runtime_settings(self, values=None, announce=True):
        values = dict(values or nexus_settings.load_user_settings())

        try:
            self.command_engine.reload_configuration()
        except Exception:
            pass

        language = str(values.get("voice_language", "auto") or "auto")
        self.current_voice_language = language
        self.pending_voice_language = "auto"

        if hasattr(self, "voice_language_combo"):
            index = self.voice_language_combo.findData(language)
            if index >= 0:
                self.voice_language_combo.blockSignals(True)
                self.voice_language_combo.setCurrentIndex(index)
                self.voice_language_combo.blockSignals(False)

        self.set_voice_mode(bool(values.get("voice_enabled", False)))

        background_voice = getattr(self, "background_voice", None)
        if background_voice is not None:
            if self.settings.legacy_openai_voice_enabled:
                background_voice.start()
            else:
                background_voice.stop()

        if hasattr(self, "assistant_model_badge"):
            self.refresh_assistant_metrics()
        self.update_dashboard_greeting()
        if announce:
            self.add_activity("NEXUS settings applied.")

    def apply_reset_preferences(self):
        self.apply_accent_color(DEFAULT_ACCENT)
        self.set_theme_mode("dark")
        self.settings.set("user_name", "")
        if hasattr(self, "user_name_input"):
            self.user_name_input.setText("")
        self.update_dashboard_greeting("")
        self.apply_runtime_settings(nexus_settings.load_user_settings(), announce=False)

    def open_settings_page(self):
        self.switch_page("settings")

    # ========================================================
    # SENDING A MESSAGE
    # ========================================================

    def handle_dashboard_command(
        self,
        command,
    ):
        """Send text typed or chosen on Home or in Chat; the reply always appears in Chat."""
        command = str(command or "").strip()
        attachment = getattr(self, "dashboard_attachment", None)
        if attachment:
            if not command:
                command = "Please review the attached file and explain its contents."
            command += (
                f"\n\n[Attached text file: {attachment['name']}]\n"
                f"{attachment['content']}\n[End attached file]"
            )
            self.clear_dashboard_attachment()

        self.dashboard_input.clear()

        if not command:
            return

        if self._current_page != "chat":
            self.switch_page("chat")

        self.process_command(command)

    def get_selected_voice_language(self):
        if hasattr(self, "voice_language_combo"):
            data = self.voice_language_combo.currentData()
            return str(data or "auto")
        return "auto"

    def set_voice_language(self, index):
        if hasattr(self, "voice_language_combo"):
            language = self.voice_language_combo.itemData(index)
            self.current_voice_language = str(language or "auto")
        else:
            self.current_voice_language = "auto"

        if self.current_voice_language == "auto":
            self.add_activity("Voice language set to Automatic.")
        else:
            labels = {
                "en": "English",
                "fr": "French",
                "sw": "Swahili",
                "es": "Spanish",
                "de": "German",
                "it": "Italian",
                "pt": "Portuguese",
                "rw": "Kinyarwanda",
            }
            self.add_activity(
                f"Voice language set to {labels.get(self.current_voice_language, self.current_voice_language)}."
            )

    def set_voice_mode(self, enabled):
        changed = self.voice_enabled != bool(enabled)
        self.voice_enabled = bool(enabled)
        for button in (getattr(self, "voice_toggle", None), getattr(self, "assistant_voice_toggle", None)):
            if button is None:
                continue
            button.blockSignals(True)
            button.setChecked(self.voice_enabled)
            button.blockSignals(False)
            composer = button.parent()
            if hasattr(composer, "_voice_toggled"):
                composer._voice_toggled(self.voice_enabled)

        if changed:
            self.add_activity("Spoken replies turned on." if self.voice_enabled else "Spoken replies turned off.")

    def _set_listening_ui(self, listening, local_route=True):
        for composer in (getattr(self, "home_composer", None), getattr(self, "chat_composer", None)):
            if composer is not None:
                composer.set_listening(listening, enabled=(local_route or not listening))

    def capture_voice_command(self):
        worker = getattr(self, "voice_worker", None)
        if worker is not None and worker.isRunning():
            # A second click while listening means "I am done talking".
            worker.finish_listening()
            return

        # Speaking over NEXUS interrupts it, and also keeps its own voice out of the microphone.
        if self.voice_output_active:
            self.interrupt_voice_output()
        local_route = VoiceCaptureWorker.route(self.settings.ai_engine) == "local"

        # The background wake listener uses the same microphone. Pause it
        # before the foreground voice capture starts.
        background_voice = getattr(self, "background_voice", None)
        if background_voice is not None:
            background_voice.stop()

        language = self.get_selected_voice_language()
        self.pending_voice_language = language

        # Give immediate visual feedback while the microphone captures speech.
        if hasattr(self, "assistant_status"):
            self.assistant_status.setText("● LISTENING")
        self._set_listening_ui(True, local_route)

        language_name = {
            "auto": "Automatic",
            "en": "English",
            "fr": "French",
            "sw": "Swahili",
            "es": "Spanish",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "rw": "Kinyarwanda",
        }.get(language, language)

        if local_route:
            voice_route = "on-device speech recognition"
        else:
            voice_route = "Gemini Live online"
        self.add_activity(f"Microphone active — {voice_route} ({language_name})…")

        current = self.conversation_manager.get_messages(self.current_conversation_id) if self.current_conversation_id is not None else []
        history = [{"role": item.get("role", "user"), "content": item.get("content", "")} for item in current[-12:]]
        self.voice_worker = VoiceCaptureWorker(language, self.settings.ai_engine, history, self, settings=self.settings)
        self.voice_worker.status.connect(self.add_activity)
        self.voice_worker.captured.connect(self.handle_voice_command)
        self.voice_worker.geminiCompleted.connect(self.handle_gemini_voice_result)
        self.voice_worker.failed.connect(self.handle_voice_error)
        self.voice_worker.finished.connect(self.finish_voice_capture)
        self.set_core_state("listening")
        self.voice_worker.start()

    def finish_voice_capture(self):
        self._set_listening_ui(False)

        # Do not overwrite THINKING/ERROR after a recognized command.
        if hasattr(self, "assistant_status"):
            current = self.assistant_status.text()
            if current == "● LISTENING":
                self.assistant_status.setText("● READY")

        if getattr(self.dashboard_core_widget, "state", "sleeping") in {"listening", "speaking"}:
            self.set_core_idle_state()
        self.voice_output_active = False

        background_voice = getattr(self, "background_voice", None)
        if background_voice is not None:
            background_voice.start()

    def handle_voice_command(self, command, detected_language):
        from core.gemini_engine import redact_secrets
        command = redact_secrets(command)
        command = command.strip()

        self.current_voice_language = str(
            detected_language
            or self.pending_voice_language
            or "auto"
        )

        self.pending_voice_language = "auto"

        if not command or command.startswith("No speech detected"):
            self.add_activity(
                command or "No speech detected."
            )
            self.show_toast("I didn't catch that. Try again a little closer to the microphone.", "info", 4000)
            if hasattr(self, "assistant_status"):
                self.assistant_status.setText("● READY")
            self.set_core_idle_state()
            return

        self.add_activity(
            f"Voice command recognized "
            f"({self.current_voice_language}): {command}"
        )

        # You spoke, so NEXUS answers aloud. This lasts for the session only; the speaker
        # button in the message box turns it off again and Settings is not changed.
        if not self.voice_enabled:
            self.set_voice_mode(True)
            self.add_activity("Voice output turned on for this session because you used the microphone.")

        if self._current_page != "chat":
            self.switch_page("chat")
        self.process_command(command)

    def handle_gemini_voice_result(self, transcript, response, audio):
        """Persist a Gemini Live turn in the existing conversation history."""
        self.set_core_state("speaking")
        self.voice_output_active = True
        from core.gemini_engine import redact_secrets
        conversation_id = self.ensure_conversation()
        user_text = redact_secrets(str(transcript or "Voice message")).strip()
        answer = redact_secrets(str(response or "")).strip()
        if not answer:
            self.handle_voice_error("Gemini Live returned no answer.")
            return
        self.conversation_manager.add_message(conversation_id, "user", user_text)
        conversation = self.conversation_manager.get_conversation(conversation_id)
        if conversation and conversation.get("title") == "New Conversation":
            self.conversation_manager.update_title(conversation_id, self.conversation_manager.create_title_from_message(user_text))
        self.conversation_manager.add_message(conversation_id, "assistant", answer)
        self.current_voice_language = self.pending_voice_language or "auto"
        self.pending_voice_language = "auto"
        self.ai_success_count += 1
        self.add_activity(f"NEXUS (Gemini Live): {answer}")
        self.refresh_conversation_list()
        self.render_current_conversation()
        self.assistant_status.setText("● READY")

    # ========================================================
    # DOCUMENT SUMMARY
    # ========================================================

    def start_document_summary(self, path_text=""):
        worker = getattr(self, "document_worker", None)
        if worker is not None and worker.isRunning():
            self.add_activity("A document summary is already in progress.")
            return
        if not path_text:
            path_text, _ = QFileDialog.getOpenFileName(
                self,
                "Choose a document to summarise",
                str(Path.home()),
                "Text documents (*.txt *.md *.csv *.log *.json *.xml *.yaml *.yml *.ini *.html *.py);;All files (*)",
            )
            if not path_text:
                self.add_activity("Document summary cancelled.")
                return

        name = Path(str(path_text).strip("\"'")).name or str(path_text)
        if self.settings.ai_engine == "online":
            where = "Gemini online (the text will leave this PC because Online mode is selected)"
        else:
            where = "the local model on this PC (the text is not uploaded)"
        self.add_activity(f"Summarising {name} with {where}...")

        conversation_id = self.ensure_conversation()
        user_text = f"Summarize the document: {name}"
        self.conversation_manager.add_message(conversation_id, "user", user_text)
        conversation = self.conversation_manager.get_conversation(conversation_id)
        if conversation and conversation.get("title") == "New Conversation":
            self.conversation_manager.update_title(
                conversation_id, self.conversation_manager.create_title_from_message(user_text)
            )
        self.refresh_conversation_list()
        self.render_current_conversation()
        self.set_core_state("thinking")
        self.assistant_status.setText("● THINKING")

        self._summary_conversation_id = conversation_id
        self.document_worker = DocumentSummaryWorker(self.command_engine.ai, path_text, self)
        self.document_worker.done.connect(self.handle_document_summary)
        self.document_worker.failed.connect(self.handle_document_summary_error)
        self.document_worker.start()

    def _finish_document_turn(self, text, ok):
        conversation_id = getattr(self, "_summary_conversation_id", None)
        if conversation_id is not None:
            self.conversation_manager.add_message(conversation_id, "assistant", text)
        self.refresh_conversation_list()
        self.render_current_conversation()
        self.set_core_idle_state()
        self.assistant_status.setText("● READY" if ok else "● ERROR")
        if self.voice_enabled:
            try:
                self.speak_response(text, self.current_voice_language)
            except Exception as error:  # noqa: BLE001
                self.add_activity(f"Voice output error: {error}")

    def handle_document_summary(self, name, summary, where):
        self.add_activity(f"Summary of {name} ready ({where}).")
        self._finish_document_turn(f"**Summary of {name}**\n\n{summary}\n\n_Produced by {where}._", True)

    def handle_document_summary_error(self, message, file_problem):
        self.add_activity(message)
        self._finish_document_turn(message, file_problem)

    def handle_voice_error(self, message):
        self.set_core_idle_state()
        self.voice_output_active = False
        if hasattr(self, "assistant_status"):
            self.assistant_status.setText("● ERROR")

        self.add_activity(
            f"Voice input unavailable: {message}"
        )
        self.show_toast(f"Voice input unavailable: {message}", "error", 6000)

    def _ensure_speech_manager(self):
        """Shared local speech engine: Kokoro, with the Windows voice as fallback."""
        if self.kokoro_speech_queue is None:
            from core.voice import KokoroSpeechQueue, VoiceService

            self.kokoro_speech_queue = KokoroSpeechQueue(self.settings)
            VoiceService._active_kokoro_queue = self.kokoro_speech_queue
        return self.kokoro_speech_queue

    def speak_response(self, response, language=None):  # noqa: F811
        """Speak a response with the configured local engine (Kokoro / Windows voice)."""
        if not response or not self.voice_enabled:
            return

        if self.settings.legacy_openai_voice_enabled:
            self._speak_response_legacy_openai(response, language)
            return

        manager = self._ensure_speech_manager()
        if manager.enqueue(response, language or self.current_voice_language or "auto"):
            self.voice_output_active = True
            self.set_core_state("speaking")
            if hasattr(self, "assistant_status"):
                self.assistant_status.setText("● SPEAKING")
        else:
            self.add_activity(f"Voice output unavailable: {manager.last_error}")

    def _poll_speech(self):
        """Report engine changes/failures and detect when speech has finished."""
        manager = self.kokoro_speech_queue
        if manager is None:
            return
        notice = manager.pop_notice()
        while notice:
            self.add_activity(notice)
            notice = manager.pop_notice()
        if self.voice_output_active and not manager.busy:
            if not (self.voice_speech_thread is not None and self.voice_speech_thread.isRunning()):
                self.voice_output_active = False
                self.set_core_idle_state(voice_output_finished=True)
                if hasattr(self, "assistant_status") and self.pending_ai_requests == 0:
                    self.assistant_status.setText("● READY")
                if manager.last_error and not manager.last_engine:
                    self.add_activity(f"Voice output unavailable: {manager.last_error}")

    def _speak_response_legacy_openai(self, response, language=None):

        if (
            self.voice_speech_thread is not None
            and self.voice_speech_thread.isRunning()
        ):
            return

        self.voice_speech_thread = QThread(self)

        self.voice_speech_worker = VoiceSpeakWorker(
            response,
            language or self.current_voice_language or self.get_selected_voice_language(),
        )

        self.voice_speech_worker.moveToThread(self.voice_speech_thread)

        self.voice_speech_thread.started.connect(self.voice_speech_worker.run)

        self.voice_speech_worker.started.connect(self.handle_voice_speech_started)

        self.voice_speech_worker.finished.connect(self.handle_voice_speech_finished)

        self.voice_speech_worker.error.connect(self.handle_voice_speech_error)

        self.voice_speech_worker.finished.connect(self.voice_speech_thread.quit)

        self.voice_speech_worker.error.connect(self.voice_speech_thread.quit)

        self.voice_speech_thread.finished.connect(
            self.voice_speech_worker.deleteLater
        )

        self.voice_speech_thread.finished.connect(self.cleanup_voice_speech)

        self.voice_speech_thread.start()

    def handle_voice_speech_started(self):  # noqa: F811
        self.set_core_state("speaking")
        self.voice_output_active = True
        self.add_activity("Nexus voice output started.")

    def handle_voice_speech_finished(self):  # noqa: F811
        was_interrupted = self.voice_output_interrupted
        self.voice_output_active = False
        self.voice_output_interrupted = False
        self.set_core_idle_state(voice_output_finished=True)
        if not was_interrupted:
            self.add_activity("Nexus voice output completed.")

    def handle_voice_speech_error(self, message):  # noqa: F811
        was_interrupted = self.voice_output_interrupted
        self.voice_output_active = False
        self.voice_output_interrupted = False
        self.set_core_idle_state(voice_output_finished=True)
        if not was_interrupted:
            self.add_activity(f"Voice output unavailable: {message}")

    def interrupt_voice_output(self):
        """Cancel active listening, or stop audio playback (never pretends to cancel AI requests)."""
        worker = getattr(self, "voice_worker", None)
        if worker is not None and worker.isRunning() and hasattr(worker, "cancel") and worker.route(worker.engine) == "local":
            worker.cancel()
            self.add_activity("Listening cancelled.")
            return True
        if not self.voice_output_active:
            return False
        try:
            from core.voice import VoiceService
            VoiceService.stop_speaking()
        except Exception as error:  # noqa: BLE001
            self.add_activity(f"Could not interrupt voice playback: {error}")
            return False
        self.voice_output_interrupted = True
        self.voice_output_active = False
        self.set_core_idle_state(voice_output_finished=True)
        self.add_activity("NEXUS voice playback interrupted by the user.")
        return True

    def cleanup_voice_speech(self):  # noqa: F811
        self.voice_speech_worker = None
        self.voice_speech_thread = None

    # ========================================================
    # WINDOWS SHELL EXECUTION
    # ========================================================

    def start_shell_command(self, command, conversation_id, response_language="auto"):
        if self.shell_thread is not None and self.shell_thread.isRunning():
            response = "NEXUS is already executing a Windows command. Please wait for it to finish."
            self.conversation_manager.add_message(conversation_id, "assistant", response)
            self.display_user_and_response(command, response)
            self.add_activity(response)
            return

        self.shell_conversation_id = conversation_id
        self.shell_response_language = response_language or "auto"
        self.shell_command = command

        self.set_core_state("thinking")
        self.assistant_status.setText("● EXECUTING")
        self.add_activity(f"NEXUS executing Windows command: {command}")

        self.shell_thread = QThread(self)
        self.shell_worker = ShellCommandWorker(command)
        self.shell_worker.moveToThread(self.shell_thread)

        self.shell_thread.started.connect(self.shell_worker.run)
        self.shell_worker.started.connect(
            lambda: self.assistant_status.setText("● EXECUTING")
        )
        self.shell_worker.finished.connect(self.handle_shell_finished)
        self.shell_worker.error.connect(self.handle_shell_error)
        self.shell_worker.finished.connect(self.shell_thread.quit)
        self.shell_worker.error.connect(self.shell_thread.quit)
        self.shell_thread.finished.connect(self.shell_worker.deleteLater)
        self.shell_thread.finished.connect(self.cleanup_shell_command)
        self.shell_thread.start()

    def handle_shell_finished(self, response, success):
        conversation_id = self.shell_conversation_id
        if conversation_id is None:
            return

        response = str(response)
        self.conversation_manager.add_message(conversation_id, "assistant", response)
        self.display_user_and_response(
            self.shell_command or "Windows command",
            response,
        )
        self.add_activity("Windows command execution completed." if success else "Windows command completed with errors.")
        self.set_core_idle_state()
        self.assistant_status.setText("● READY" if success else "● ERROR")
        self._thinking_active = False
        self.render_current_conversation()

        if self.voice_enabled:
            try:
                self.speak_response(response, self.shell_response_language)
            except Exception as error:
                self.add_activity(f"Voice output error: {error}")

    def handle_shell_error(self, message):
        conversation_id = self.shell_conversation_id
        response = f"Windows command execution failed: {message}"
        if conversation_id is not None:
            self.conversation_manager.add_message(conversation_id, "assistant", response)
            self.display_user_and_response(
                self.shell_command or "Windows command",
                response,
            )
        self.add_activity(response)
        self._thinking_active = False
        self.set_core_idle_state()
        self.assistant_status.setText("● ERROR")
        self.render_current_conversation()

    def cleanup_shell_command(self):
        self.shell_worker = None
        self.shell_thread = None
        self.shell_conversation_id = None
        self.shell_response_language = "auto"
        self.shell_command = ""

    # ========================================================
    # QUICK COMMAND EXECUTION
    # ========================================================

    def run_quick_command(
        self,
        command,
    ):

        self.switch_page("assistant")

        self.assistant_input.setPlainText(command)

        self.process_command(command)

    # ========================================================
    # CLOCK & ASSISTANT STATE
    # ========================================================

    def update_dashboard_clock(self):
        from datetime import datetime
        now = datetime.now()
        if hasattr(self, "dashboard_date"):
            self.dashboard_date.setText(now.strftime("%A, %d %B") + "  ·  " + now.strftime("%H:%M"))
        if hasattr(self, "dashboard_clock"):
            self.dashboard_clock.setText(now.strftime("%H:%M:%S"))
        if now.second == 0 and now.minute == 0:
            self.update_dashboard_greeting()

    def set_core_state(self, state):
        core = getattr(self, "dashboard_core_widget", None)
        if core is not None:
            core.set_state(state)
        state = getattr(core, "state", state)
        voice_bar = getattr(self, "voice_bar", None)
        if voice_bar is not None:
            worker = getattr(self, "voice_worker", None)
            can_finish = True
            if worker is not None and worker.isRunning():
                can_finish = VoiceCaptureWorker.route(worker.engine) == "local"
            voice_bar.set_state(state, can_finish)
        self._set_orb_text(state)

    def set_core_idle_state(self, voice_output_finished=False):
        """Choose the truthful non-thinking state without hiding concurrent work."""
        if getattr(self, "pending_ai_requests", 0) > 0:
            self.set_core_state("thinking")
            return

        core = getattr(self, "dashboard_core_widget", None)
        current = getattr(core, "state", "sleeping")
        voice_worker = getattr(self, "voice_worker", None)
        if voice_worker is not None and voice_worker.isRunning():
            self.set_core_state(current if current in {"listening", "speaking"} else "listening")
            return

        speech_thread = getattr(self, "voice_speech_thread", None)
        if speech_thread is not None and speech_thread.isRunning() and not voice_output_finished:
            self.set_core_state("speaking")
            return

        self.set_core_state("sleeping")

    # ========================================================
    # CHAT PAGE
    # ========================================================

    def create_chat_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("chatHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(28, 16, 20, 14)
        header_layout.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.current_conversation_title_label = ElidedLabel("New conversation")
        self.current_conversation_title_label.setObjectName("cardTitle")
        self.current_conversation_title_label.setStyleSheet("font-size: 16px;")
        titles.addWidget(self.current_conversation_title_label)
        self.conversation_meta_label = QLabel()
        self.conversation_meta_label.setObjectName("faintText")
        titles.addWidget(self.conversation_meta_label)
        header_layout.addLayout(titles, 1)
        self.assistant_status = StatusPill("● READY")
        self.assistant_status.mirrors.append(self.home_status)
        header_layout.addWidget(self.assistant_status)
        self.assistant_model_badge = QLabel()
        self.assistant_model_badge.setObjectName("badge")
        header_layout.addWidget(self.assistant_model_badge)
        self.rename_button = IconButton("edit", "Rename conversation")
        self.rename_button.clicked.connect(
            lambda: self.current_conversation_id is not None and self.rename_conversation(self.current_conversation_id)
        )
        header_layout.addWidget(self.rename_button)
        self.delete_button = IconButton("trash", "Delete conversation")
        self.delete_button.clicked.connect(
            lambda: self.current_conversation_id is not None and self.delete_conversation(self.current_conversation_id)
        )
        header_layout.addWidget(self.delete_button)
        new_chat = IconButton("plus", "New chat (Ctrl+N)")
        new_chat.clicked.connect(self.start_new_conversation)
        header_layout.addWidget(new_chat)
        layout.addWidget(header)
        divider = QFrame()
        divider.setObjectName("divider")
        layout.addWidget(divider)

        self.assistant_output = ChatView(SUGGESTIONS)
        self.assistant_output.copyRequested.connect(self._copy_text)
        self.assistant_output.speakRequested.connect(self.read_aloud)
        self.assistant_output.suggestionChosen.connect(self.handle_dashboard_command)
        self.assistant_output.settingsRequested.connect(lambda: self.switch_page("settings"))
        layout.addWidget(self.assistant_output, 1)

        bottom = QWidget()
        bottom_row = QHBoxLayout(bottom)
        bottom_row.setContentsMargins(24, 6, 24, 14)
        bottom_row.addStretch(1)
        column = QWidget()
        column.setMaximumWidth(820)
        column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)
        self.voice_bar = VoiceBar()
        self.voice_bar.doneRequested.connect(self.capture_voice_command)
        self.voice_bar.cancelRequested.connect(self.interrupt_voice_output)
        column_layout.addWidget(self.voice_bar)

        self.chat_composer = Composer("Message NEXUS…")
        self.assistant_input = self.chat_composer.input
        self.assistant_input.setObjectName("composerInput")
        self.assistant_input.sendRequested.connect(self.handle_chat_command)
        self.assistant_input.clearRequested.connect(self.clear_assistant_chat)
        self.assistant_input.newConversationRequested.connect(self.start_new_conversation)
        self.assistant_mic_button = self.chat_composer.mic_button
        self.assistant_mic_button.clicked.connect(self.capture_voice_command)
        self.assistant_voice_toggle = self.chat_composer.voice_toggle
        self.assistant_voice_toggle.toggled.connect(self.set_voice_mode)
        self.voice_language_combo = self.chat_composer.language_combo
        self.voice_language_combo.currentIndexChanged.connect(self.set_voice_language)
        self.chat_composer.attach_button.clicked.connect(self.attach_dashboard_file)
        self.chat_composer.remove_attachment_button.clicked.connect(self.clear_dashboard_attachment)
        column_layout.addWidget(self.chat_composer)
        hint = QLabel("Enter to send  ·  Shift+Enter for a new line  ·  Ctrl+M to talk  ·  Esc stops voice")
        hint.setObjectName("kbdHint")
        hint.setAlignment(Qt.AlignCenter)
        column_layout.addWidget(hint)
        bottom_row.addWidget(column, 100)
        bottom_row.addStretch(1)
        layout.addWidget(bottom)
        self.refresh_assistant_metrics()
        return page

    def handle_chat_command(self, command):
        self.handle_dashboard_command(command)

    def refresh_assistant_metrics(self):
        if not hasattr(self, "assistant_output"):
            return
        model = getattr(self.settings, "ai_model", nexus_settings.NEXUS_MODEL)
        mode = self.settings.ai_engine
        labels = {
            "automatic": f"Automatic · {model}",
            "online": f"Gemini · {self.settings.gemini_text_model}",
            "local": f"Local · {model}",
        }
        engine_text = labels.get(mode, str(model))
        from core.gemini_engine import gemini_is_configured
        tooltip = {
            "automatic": "Answers come from the local model on this PC; a few request types use Gemini if a key is set.",
            "online": "Answers come from Google Gemini online.",
            "local": "Answers come from the local model on this PC. Nothing leaves your computer.",
        }.get(mode, "")
        tooltip += (" Gemini key configured." if gemini_is_configured() else " No Gemini key configured.")
        for label in (getattr(self, "assistant_model_badge", None), getattr(self, "dashboard_engine_label", None)):
            if label is not None:
                label.setText(engine_text)
                label.setToolTip(tooltip.strip())
        if hasattr(self, "engine_status_label"):
            self.engine_status_label.setText(f"● {engine_text}")
            self.engine_status_label.setToolTip(tooltip.strip())

        conversation = None
        if self.current_conversation_id is not None:
            conversation = self.conversation_manager.get_conversation(self.current_conversation_id)
        has_conversation = bool(conversation)
        if hasattr(self, "current_conversation_title_label"):
            self.current_conversation_title_label.setText(
                str(conversation.get("title", "New conversation")) if conversation else "New conversation"
            )
        if hasattr(self, "conversation_meta_label"):
            if conversation:
                count = self.assistant_output.message_count()
                stamp = friendly_time(conversation.get("updated_at") or conversation.get("created_at"))
                self.conversation_meta_label.setText(
                    f"{count} message{'s' if count != 1 else ''}" + (f"  ·  last active {stamp}" if stamp else "")
                )
            else:
                self.conversation_meta_label.setText("Start typing or press the microphone to talk")
        for button in (getattr(self, "rename_button", None), getattr(self, "delete_button", None)):
            if button is not None:
                button.setEnabled(has_conversation)

    def send_assistant_message(self):
        if not hasattr(self, "assistant_input"):
            return
        command = self.assistant_input.toPlainText().strip()
        if not command:
            self.assistant_input.setFocus()
            return
        self.assistant_input.clear()
        self.process_command(command)

    # ========================================================
    # SYSTEM PAGE
    # ========================================================

    def create_system_page(self):
        palette = current_palette()
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(18)
        header = PageHeader("System", "Live health of this PC, measured locally every two seconds.")
        root.addWidget(header)

        stats = ResponsiveGrid(min_column_width=210, max_columns=4, spacing=14)
        self.system_stat_cards = {}
        for key, title, icon, color in (
            ("cpu", "Processor", "system", palette.accent),
            ("memory", "Memory", "ram", STATE_COLORS["thinking"]),
            ("disk", "Storage", "storage", STATE_COLORS["speaking"]),
            ("battery", "Battery", "battery", STATE_COLORS["listening"]),
        ):
            card = Card()
            top = QHBoxLayout()
            top.setSpacing(8)
            top.addWidget(IconLabel(icon, 16, "muted"))
            label = QLabel(title)
            label.setObjectName("statLabel")
            top.addWidget(label)
            top.addStretch(1)
            card.body.addLayout(top)
            value = QLabel("—")
            value.setObjectName("statValue")
            card.body.addWidget(value)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setAccessibleName(f"{title} usage")
            card.body.addWidget(bar)
            detail = QLabel("Measuring…")
            detail.setObjectName("faintText")
            card.body.addWidget(detail)
            spark = Sparkline(color)
            card.body.addWidget(spark)
            stats.add(card)
            self.system_stat_cards[key] = {"value": value, "bar": bar, "detail": detail, "spark": spark}
        root.addWidget(stats)

        lower = ResponsiveGrid(min_column_width=380, max_columns=2, spacing=14)
        graph_card = Card("Usage over time", icon="activity")
        legend = QHBoxLayout()
        legend.setSpacing(16)
        for name, color in (("Processor", palette.accent), ("Memory", STATE_COLORS["thinking"])):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color};")
            legend.addWidget(dot)
            text = QLabel(name)
            text.setObjectName("faintText")
            legend.addWidget(text)
        legend.addStretch(1)
        graph_card.body.addLayout(legend)
        self.system_page_graph = UsageGraph({"cpu": palette.accent, "memory": STATE_COLORS["thinking"]})
        graph_card.body.addWidget(self.system_page_graph)
        lower.add(graph_card, span=2)

        live_card = Card("Live readings", icon="bolt")
        self.system_live_rows = {}
        for key, label in (
            ("cpu_temp", "CPU temperature"),
            ("gpu_load", "GPU load"),
            ("download", "Download"),
            ("upload", "Upload"),
            ("uptime", "Time since start-up"),
        ):
            live_card.body.addLayout(self._system_info_row(label, key, self.system_live_rows))
        live_card.body.addStretch(1)
        lower.add(live_card)

        info_card = Card("This PC", icon="info")
        self.system_info_labels = {}
        for key, label in (
            ("os", "Windows"),
            ("cpu", "Processor"),
            ("ram", "Installed memory"),
            ("gpu", "Graphics"),
            ("storage", "System drive"),
            ("hostname", "Computer name"),
            ("ip", "Local IP address"),
        ):
            info_card.body.addLayout(self._system_info_row(label, key, self.system_info_labels, "Loading…"))
        info_card.body.addStretch(1)
        lower.add(info_card)
        root.addWidget(lower)

        checks = Card("Ask NEXUS about this PC", icon="sparkle")
        buttons = FlowLayout(spacing=8, center=False)
        holder = QWidget()
        holder.setLayout(buttons)
        for label, prompt in (
            ("System summary", "system"),
            ("Battery status", "battery"),
            ("Running processes", "show running processes"),
        ):
            button = QPushButton(label)
            button.setObjectName("chip")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, text=prompt: self.handle_dashboard_command(text))
            buttons.addWidget(button)
        checks.body.addWidget(holder)
        root.addWidget(checks)
        root.addStretch(1)
        return scroll_page(content)

    @staticmethod
    def _system_info_row(label, key, store, placeholder="—"):
        row = QHBoxLayout()
        row.setSpacing(12)
        name = QLabel(label)
        name.setObjectName("mutedText")
        row.addWidget(name)
        row.addStretch(1)
        value = QLabel(placeholder)
        value.setObjectName("rowTitle")
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(value, 2)
        store[key] = value
        return row

    def _load_static_system_info(self):
        """Load identifiers that do not need to be queried every refresh."""
        if self._system_static_info is not None:
            return self._system_static_info

        # This method can be reached by more than one UI refresh path.  Build the
        # snapshot once and keep subprocess work from racing with itself.
        if getattr(self, "_loading_static_system_info", False):
            return self._system_static_info or {}
        self._loading_static_system_info = True

        os_name = f"{platform.system()} {platform.release()}"
        build = platform.version()
        cpu_name = platform.processor() or "Unavailable"

        if os.name == "nt":
            powershell = os.path.join(
                os.environ.get("SystemRoot", r"C:\Windows"),
                "System32",
                "WindowsPowerShell",
                "v1.0",
                "powershell.exe",
            )
            try:
                result = subprocess.run(
                    [powershell, "-NoProfile", "-Command", "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; (Get-ComputerInfo -Property WindowsProductName,WindowsVersion | ConvertTo-Json -Compress)"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    check=False,
                )
                import json
                product = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
                os_product = str(product.get("WindowsProductName") or "").strip()
                os_version = str(product.get("WindowsVersion") or "").strip()
                if os_product:
                    os_name = os_product
                if os_version:
                    build = os_version
            except Exception:  # noqa: BLE001
                pass

            try:
                result = subprocess.run(
                    [powershell, "-NoProfile", "-Command", "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    check=False,
                )
                friendly_cpu = result.stdout.strip()
                if friendly_cpu:
                    cpu_name = friendly_cpu
            except Exception:  # noqa: BLE001
                pass

        if not cpu_name or cpu_name.lower() in {"generic", "unknown"}:
            cpu_name = "Unavailable"

        hostname = socket.gethostname() or "Unavailable"
        ip_address = "Unavailable"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                ip_address = sock.getsockname()[0]
        except OSError:
            try:
                ip_address = socket.gethostbyname(hostname)
            except OSError:
                pass

        ram_total_gb = None
        if psutil is not None:
            try:
                ram_total_gb = psutil.virtual_memory().total / (1024 ** 3)
            except Exception:  # noqa: BLE001
                pass

        gpu_name = "Unavailable"
        gpu_load = None
        gpu_temp = None
        if os.name == "nt":
            nvidia = shutil.which("nvidia-smi")
            if nvidia:
                try:
                    result = subprocess.run(
                        [nvidia, "--query-gpu=name,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=10,
                        check=False,
                    )
                    line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
                    parts = [item.strip() for item in line.split(",")]
                    if parts:
                        gpu_name = parts[0] or gpu_name
                    if len(parts) > 1 and parts[1].isdigit():
                        gpu_load = float(parts[1])
                    if len(parts) > 2 and parts[2].isdigit():
                        gpu_temp = float(parts[2])
                except Exception:  # noqa: BLE001
                    pass

            if gpu_name == "Unavailable":
                powershell = os.path.join(
                    os.environ.get("SystemRoot", r"C:\\Windows"),
                    "System32",
                    "WindowsPowerShell",
                    "v1.0",
                    "powershell.exe",
                )
                try:
                    result = subprocess.run(
                        [powershell, "-NoProfile", "-Command", "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; (Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join '; '"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=10,
                        check=False,
                    )
                    value = result.stdout.strip()
                    if value:
                        gpu_name = value
                except Exception:  # noqa: BLE001
                    pass

        self._system_static_info = {
            "os": f"{os_name} · {build}" if build else os_name,
            "cpu": cpu_name,
            "ram_total_gb": ram_total_gb,
            "gpu": gpu_name,
            "gpu_load": gpu_load,
            "gpu_temp": gpu_temp,
            "hostname": hostname,
            "ip": ip_address,
        }
        self._loading_static_system_info = False
        return self._system_static_info

    def _apply_static_system_info(self):
        info = self._system_static_info or {}
        for key, value in {
            "os": info.get("os", "Unavailable"),
            "cpu": info.get("cpu", "Unavailable"),
            "ram": (
                f"{info['ram_total_gb']:.1f} GB"
                if info.get("ram_total_gb") is not None else "Unavailable"
            ),
            "gpu": info.get("gpu", "Unavailable"),
            "hostname": info.get("hostname", "Unavailable"),
            "ip": info.get("ip", "Unavailable"),
        }.items():
            label = self.system_info_labels.get(key) if hasattr(self, "system_info_labels") else None
            if label is not None:
                label.setText(str(value))

    def _ensure_static_system_info(self):
        """Windows/CPU/GPU names come from slow PowerShell queries, so read them once, off the UI thread."""
        if self._system_static_info is not None:
            self._apply_static_system_info()
            return
        if self._static_thread is not None and self._static_thread.is_alive():
            return

        def work():
            try:
                info = self._load_static_system_info()
            except Exception:  # noqa: BLE001
                info = None
            if not getattr(self, "_quitting", False):
                self._telemetry_bridge.static_ready.emit(info)

        self._static_thread = threading.Thread(target=work, name="NEXUS-SystemInfo", daemon=True)
        self._static_thread.start()

    def _update_gpu_telemetry(self):
        """Read optional NVIDIA GPU telemetry without inventing data for other GPUs."""
        info = self._system_static_info or {}
        if os.name != "nt":
            return None, None
        nvidia = shutil.which("nvidia-smi")
        if not nvidia:
            return info.get("gpu_load"), info.get("gpu_temp")
        try:
            result = subprocess.run(
                [nvidia, "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1.5,
                check=False,
            )
            line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
            parts = [item.strip() for item in line.split(",")]
            load = float(parts[0]) if len(parts) > 0 and parts[0].replace(".", "", 1).isdigit() else None
            temp = float(parts[1]) if len(parts) > 1 and parts[1].replace(".", "", 1).isdigit() else None
            return load, temp
        except Exception:  # noqa: BLE001
            return info.get("gpu_load"), info.get("gpu_temp")

    def _update_network_rates(self):
        if psutil is None:
            self._network_download_mbps = 0.0
            self._network_upload_mbps = 0.0
            return
        try:
            counters = psutil.net_io_counters()
            now = time.monotonic()
            if self._network_sample is not None:
                previous_time, previous_recv, previous_sent = self._network_sample
                elapsed = max(0.001, now - previous_time)
                self._network_download_mbps = max(0.0, counters.bytes_recv - previous_recv) / elapsed / (1024 ** 2)
                self._network_upload_mbps = max(0.0, counters.bytes_sent - previous_sent) / elapsed / (1024 ** 2)
            self._network_sample = (now, counters.bytes_recv, counters.bytes_sent)
        except Exception:  # noqa: BLE001
            self._network_download_mbps = 0.0
            self._network_upload_mbps = 0.0

    def _read_cpu_temperature(self):
        if psutil is None:
            return None
        try:
            sensors = psutil.sensors_temperatures()
        except Exception:  # noqa: BLE001
            return None
        candidates = []
        for name, entries in (sensors or {}).items():
            low = str(name).lower()
            for entry in entries:
                label = str(getattr(entry, "label", "") or "").lower()
                current = getattr(entry, "current", None)
                if current is None or not (0 < float(current) < 130):
                    continue
                score = 0
                if any(token in low or token in label for token in ("cpu", "package", "core", "tctl", "tdie")):
                    score += 2
                candidates.append((score, float(current)))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
        return None

    @staticmethod
    def _format_uptime():
        if psutil is None:
            return "Unavailable"
        try:
            seconds = max(0, int(time.time() - psutil.boot_time()))
            days, remainder = divmod(seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes = remainder // 60
            if days:
                return f"{days}d {hours:02d}h {minutes:02d}m"
            return f"{hours}h {minutes:02d}m"
        except Exception:  # noqa: BLE001
            return "Unavailable"

    def _refresh_system_logs(self):
        if not hasattr(self, "system_logs_output"):
            return
        text = "\n".join(self._system_log_entries[-8:]) or "Waiting for telemetry…"
        self.system_logs_output.setPlainText(text)
        cursor = self.system_logs_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.system_logs_output.setTextCursor(cursor)

    def _append_system_log(self, message):
        from datetime import datetime
        stamp = datetime.now().strftime("%H:%M:%S")
        entry = f"● {stamp}   {message}"
        self._system_log_entries.append(entry)
        self._system_log_entries = self._system_log_entries[-30:]
        self._refresh_system_logs()

    def show_system_info(self):
        self.switch_page("system")
        self.add_activity("System information opened.")

    def show_battery_info(self):
        self.switch_page("system")
        battery = getattr(self, "battery_value", None)
        if battery is None:
            self.add_activity("Battery information is unavailable on this PC.")
        else:
            charging = "charging" if battery.get("charging") else "not charging"
            self.add_activity(f"Battery: {battery.get('percent', 0):.0f}% ({charging}).")

    def show_network_info(self):
        self.switch_page("system")
        self.add_activity(
            f"Network: {self._network_download_mbps:.2f} MB/s down, {self._network_upload_mbps:.2f} MB/s up."
        )

    def show_process_list(self):
        self.switch_page("assistant")
        self.assistant_input.setPlainText("show running processes")
        self.process_command("show running processes")

    def show_disk_usage(self):
        self.switch_page("system")
        self.add_activity(f"Storage usage: {self.storage_value or 0:.1f}%.")

    def show_temperature_info(self):
        self.switch_page("system")
        temp = self._read_cpu_temperature()
        if temp is None:
            self.add_activity("CPU temperature is unavailable through the supported local sensors.")
        else:
            self.add_activity(f"CPU temperature: {temp:.1f}°C.")

    def update_system_stats(self):
        """Sample telemetry on a worker thread: psutil's CPU reading blocks for half a second."""
        if self._telemetry_busy or getattr(self, "_quitting", False):
            return
        self._telemetry_busy = True

        def work():
            payload = {}
            try:
                payload["info"] = SystemMonitor.get_system_info()
                self._update_network_rates()
                payload["cpu_temp"] = self._read_cpu_temperature()
                payload["gpu"] = self._update_gpu_telemetry()
                payload["uptime"] = self._format_uptime()
                payload["disk_text"] = self._format_gb_used_total(payload["info"].get("disk", 0) or 0)
                if psutil is not None:
                    try:
                        frequency = psutil.cpu_freq()
                        payload["cpu_freq"] = frequency.current / 1000.0 if frequency else None
                        payload["cores"] = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 0
                        vm = psutil.virtual_memory()
                        payload["memory_text"] = f"{vm.used / (1024 ** 3):.1f} of {vm.total / (1024 ** 3):.1f} GB in use"
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as error:  # noqa: BLE001
                payload["error"] = str(error)
            if not getattr(self, "_quitting", False):
                self._telemetry_bridge.ready.emit(payload)

        self._telemetry_thread = threading.Thread(target=work, name="NEXUS-Telemetry", daemon=True)
        self._telemetry_thread.start()

    def _apply_telemetry(self, payload):
        """Show a telemetry sample. Runs on the UI thread."""
        self._telemetry_busy = False
        if getattr(self, "_quitting", False):
            return
        if payload.get("error"):
            print(f"System monitor error: {payload['error']}")
            return
        info = payload.get("info") or {}
        cpu = float(info.get("cpu", 0) or 0)
        memory = float(info.get("memory", 0) or 0)
        storage = float(info.get("disk", 0) or 0)
        battery = info.get("battery")
        network = float(info.get("network", 0) or 0)

        self.cpu_value = cpu
        self.memory_value = memory
        self.storage_value = storage
        self.battery_value = battery
        self.cpu_history.append(cpu)
        self.memory_history.append(memory)
        self.disk_history.append(storage)
        self.network_history.append(min(100, network * 10))
        for history in (self.cpu_history, self.memory_history, self.disk_history, self.network_history):
            if len(history) > self.max_graph_points:
                del history[:-self.max_graph_points]
        self.refresh_dashboard_metrics()

        cards = getattr(self, "system_stat_cards", {})
        battery_percent = None if battery is None else float(battery.get("percent", 0))
        frequency = payload.get("cpu_freq")
        cores = payload.get("cores")
        details = {
            "cpu": (f"{frequency:.1f} GHz · {cores} cores" if frequency else (f"{cores} cores" if cores else "")),
            "memory": payload.get("memory_text", ""),
            "disk": payload.get("disk_text", ""),
            "battery": ("Not available on this PC" if battery is None
                        else ("Charging" if battery.get("charging") else "On battery power")),
        }
        for key, value, history in (
            ("cpu", cpu, self.cpu_history),
            ("memory", memory, self.memory_history),
            ("disk", storage, self.disk_history),
            ("battery", battery_percent, [battery_percent] if battery_percent is not None else []),
        ):
            card = cards.get(key)
            if card is None:
                continue
            card["value"].setText("N/A" if value is None else f"{value:.0f}%")
            number = 0 if value is None else int(max(0, min(100, value)))
            card["bar"].setValue(number)
            level = "ok"
            if key != "battery" and number >= 90:
                level = "high"
            elif key != "battery" and number >= 75:
                level = "warn"
            elif key == "battery" and value is not None and number <= 15 and not battery.get("charging"):
                level = "high"
            if card["bar"].property("level") != level:
                card["bar"].setProperty("level", level)
                repolish(card["bar"])
            card["detail"].setText(details.get(key) or "")
            card["spark"].setData(history)

        live = getattr(self, "system_live_rows", {})
        if live:
            cpu_temp = payload.get("cpu_temp")
            gpu_load, _gpu_temp = payload.get("gpu") or (None, None)
            live["cpu_temp"].setText(f"{cpu_temp:.1f} °C" if cpu_temp is not None else "Not reported")
            live["gpu_load"].setText(f"{gpu_load:.0f}%" if gpu_load is not None else "Not reported")
            live["download"].setText(f"{self._network_download_mbps:.2f} MB/s")
            live["upload"].setText(f"{self._network_upload_mbps:.2f} MB/s")
            live["uptime"].setText(payload.get("uptime", "Unavailable"))
        if hasattr(self, "system_info_labels") and payload.get("disk_text"):
            self.system_info_labels["storage"].setText(payload["disk_text"])
        if hasattr(self, "system_page_graph"):
            self.system_page_graph.set_series("cpu", self.cpu_history)
            self.system_page_graph.set_series("memory", self.memory_history)

        # Only add a telemetry log periodically or when battery state changes.
        now = time.monotonic()
        battery_state = None if battery is None else (round(float(battery.get("percent", 0))), bool(battery.get("charging")))
        if battery_state != self._last_battery_log and battery_state is not None:
            charging_text = "Charging" if battery_state[1] else "Not charging"
            self._append_system_log(f"Battery status: {charging_text} ({battery_state[0]}%)")
            self._last_battery_log = battery_state
        if now - self._last_system_log >= 10:
            self._append_system_log(
                f"Telemetry refresh · CPU {cpu:.0f}% · Memory {memory:.0f}% · Disk {storage:.0f}%"
            )
            self._last_system_log = now

    @staticmethod
    def _format_gb_used_total(disk_percent):
        try:
            anchor = Path.home().anchor or os.environ.get("SystemDrive", "C:\\")
            usage = __import__("shutil").disk_usage(anchor)
            used_gb = usage.used / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            return f"{used_gb:.1f} GB / {total_gb:.1f} GB"
        except Exception:  # noqa: BLE001
            return f"{float(disk_percent):.0f}% used"

    # ========================================================
    # CONVERSATION HELPERS
    # ========================================================

    def ensure_conversation(self):

        if self.current_conversation_id is not None:
            conversation = self.conversation_manager.get_conversation(
                self.current_conversation_id
            )

            if conversation:
                return self.current_conversation_id

        conversation_id = self.conversation_manager.create_conversation()

        self.current_conversation_id = conversation_id

        return conversation_id

    # ========================================================
    # START NEW CONVERSATION
    # ========================================================

    def restore_latest_conversation(self):

        try:

            conversations = (
                self.conversation_manager
                .get_conversations()
            )

            if not conversations:

                self.current_conversation_id = None
                return

            latest = conversations[0]

            conversation_id = latest.get(
                "id"
            )

            if conversation_id is None:
                return

            self.load_conversation(
                conversation_id
            )

        except Exception as error:  # noqa: BLE001

            print(
                "Could not restore latest conversation:",
                error,
            )

    def start_new_conversation(self):

        self.current_conversation_id = None

        self.assistant_input.clear()

        if hasattr(
            self,
            "dashboard_input",
        ):
            self.dashboard_input.clear()

        self._thinking_active = False
        self.thinking_timer.stop()
        self.assistant_status.setText("● READY")

        self.add_activity("New conversation ready.")

        self.switch_page("assistant")

        self.render_current_conversation()

        self.refresh_conversation_list()

        self.assistant_input.setFocus()

    # ========================================================
    # REFRESH CONVERSATION LIST
    # ========================================================

    @staticmethod
    def _format_record_time(value):
        return friendly_time(value) or "Local"

    def refresh_conversation_list(self):
        if not hasattr(self, "conversation_list"):
            return
        current_id = self.current_conversation_id
        conversations = self.conversation_manager.get_conversations()
        self.conversation_list.blockSignals(True)
        self.conversation_list.clear()
        selected_item = None
        for conversation in conversations:
            conversation_id = conversation.get("id")
            title = conversation.get("title", "New Conversation")
            stamp = friendly_time(conversation.get("updated_at") or conversation.get("created_at"), with_time=False)
            item = QListWidgetItem()
            # The row widget is the only place where the title is rendered.
            # Keep BOTH DisplayRole and normal item text empty so QListWidget's
            # delegate cannot paint a second copy of the conversation title.
            item.setText("")
            item.setData(Qt.DisplayRole, "")
            item.setData(Qt.UserRole, conversation_id)
            item.setData(Qt.UserRole + 1, str(title))
            item.setData(Qt.AccessibleTextRole, str(title))
            item.setToolTip(str(title))
            item.setSizeHint(QSize(0, 38))
            self.conversation_list.addItem(item)
            self.conversation_list.setItemWidget(
                item,
                self.create_conversation_row(title, stamp),
            )
            if current_id is not None and conversation_id == current_id:
                selected_item = item
        if selected_item is not None:
            self.conversation_list.setCurrentItem(selected_item)
        else:
            self.conversation_list.clearSelection()
        self.conversation_list.blockSignals(False)
        if hasattr(self, "history_empty"):
            self.history_empty.setVisible(not conversations)
            self.history_empty_spacer.setVisible(not conversations)
            self.conversation_list.setVisible(bool(conversations))
        self.refresh_assistant_metrics()
        query = self.search_input.text() if hasattr(self, "search_input") else ""
        self.filter_conversations(query)
        self._schedule_data_refresh()

    # ========================================================
    # LOAD CONVERSATION FROM LIST
    # ========================================================

    def load_conversation_from_item(
        self,
        item,
    ):

        conversation_id = item.data(Qt.UserRole)

        if conversation_id is None:
            return

        self.load_conversation(conversation_id)

    # ========================================================
    # LOAD CONVERSATION
    # ========================================================

    def load_conversation(self, conversation_id):
        conversation = self.conversation_manager.get_conversation(conversation_id)
        if not conversation:
            return
        self.current_conversation_id = conversation_id
        self._thinking_active = bool(conversation_id in self.ai_threads)
        if not self._thinking_active:
            self.thinking_timer.stop()
            self.assistant_status.setText("● READY")
        self.switch_page("assistant")
        self.render_current_conversation()
        self.refresh_conversation_list()

    # ========================================================
    # PROCESS COMMAND
    # ========================================================

    def process_command(
        self,
        command,
    ):

        from core.gemini_engine import redact_secrets
        command = redact_secrets(command).strip()

        if not command:
            return

        # "summarize C:\\notes\\report.txt" reads that file; ordinary questions fall through to the AI.
        from core.documents import parse_summarize_request
        document_request = parse_summarize_request(command)
        if document_request is not None:
            self.assistant_input.clear()
            self.start_document_summary(document_request)
            return

        self.set_core_state("thinking")

        conversation_id = self.ensure_conversation()

        response_language = self.pending_voice_language
        self.pending_voice_language = "auto"

        self.conversation_manager.add_message(
            conversation_id,
            "user",
            command,
        )

        conversation = self.conversation_manager.get_conversation(conversation_id)

        if conversation and conversation["title"] == "New Conversation":

            title = self.conversation_manager.create_title_from_message(command)

            self.conversation_manager.update_title(
                conversation_id,
                title,
            )

        self.refresh_conversation_list()

        # ----------------------------------------------------
        # CLEAR INPUT
        # ----------------------------------------------------

        self.assistant_input.clear()

        # ----------------------------------------------------
        # LOCAL COMMANDS
        # ----------------------------------------------------

        command_lower = command.lower()

        local_commands = {
            "help",
            "status",
            "system",
            "battery",
            "time",
            "about",
            "new",
            "clear",
        }
        
        # Windows shell commands execute in a worker so the UI never blocks
        # while PowerShell/CMD is running.
        is_shell_command = self.command_engine.is_shell_command(command)

        if is_shell_command:
            if self.command_engine.shell_requires_confirmation(command):
                answer = QMessageBox.question(
                    self,
                    "Confirm Windows command",
                    "NEXUS is about to execute this Windows shell command:\n\n"
                    f"{command}\n\nContinue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    response = "Windows command cancelled."
                    self.conversation_manager.add_message(conversation_id, "assistant", response)
                    self.display_user_and_response(command, response)
                    self.add_activity(response)
                    self.set_core_idle_state()
                    return

            self.start_shell_command(command, conversation_id, response_language)
            return

        # Phase 5: send recognized local PC-control requests to the
        # CommandEngine instead of unnecessarily sending them to Ollama.
        is_pc_command = self.command_engine.is_pc_command(command)

        if command_lower in local_commands or is_pc_command:

            question = self.command_engine.pc_confirmation_prompt(command)
            if question and QMessageBox.question(
                self, "Confirm file action", question, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes:
                response = "Cancelled. Nothing was changed."
            else:
                response = self.command_engine.execute(command)

            if response == "__OPEN_NEXUS__":
                self.activate_nexus()
                response = "NEXUS is open."

            if response == "__CLEAR__":

                self.clear_activity()
                self.set_core_idle_state()

                self.conversation_manager.add_message(
                    conversation_id,
                    "assistant",
                    "Activity console cleared.",
                )

                return

            self.conversation_manager.add_message(
                conversation_id,
                "assistant",
                response,
            )

            self.display_user_and_response(
                command,
                response,
            )

            self.add_activity(response)
            self.set_core_idle_state()

            if self.voice_enabled:
                try:
                    self.speak_response(response, response_language)
                except Exception as error:  # noqa: BLE001
                    self.add_activity(f"Voice output error: {error}")

            return

        # ----------------------------------------------------
        # AI REQUEST
        # ----------------------------------------------------

        self.ai_request_count += 1
        self.pending_ai_requests += 1
        self.response_started_at[conversation_id] = __import__("datetime").datetime.now()
        messages = self.conversation_manager.get_messages(conversation_id)

        conversation_history = []

        for message in messages[:-1]:

            conversation_history.append(
                {
                    "role": message["role"],
                    "content": message["content"],
                }
            )

        self.assistant_status.setText("● THINKING")

        self.add_activity(f"Nexus processing: {command}")

        safe_command = escape(command)
        self.thinking_command = command
        self.thinking_index = 0
        self.start_thinking_indicator(safe_command)

        self.ai_voice_languages[conversation_id] = response_language

        thread = QThread()

        worker = AIWorker(
            self.command_engine.ai,
            conversation_id,
            command,
            conversation_history,
            speech_enabled=self.voice_enabled,
            speech_language=response_language,
        )

        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        worker.chunk.connect(self.handle_ai_stream_chunk)
        worker.speech_chunk.connect(self.handle_ai_speech_chunk)

        worker.finished.connect(self.handle_ai_response)

        worker.error.connect(self.handle_ai_error)

        worker.finished.connect(thread.quit)

        worker.error.connect(thread.quit)

        thread.finished.connect(worker.deleteLater)

        thread.finished.connect(self.cleanup_ai_worker)

        self.ai_threads[conversation_id] = thread

        self.ai_workers[conversation_id] = worker

        thread.start()

    # ========================================================
    # DISPLAY USER + RESPONSE
    # ========================================================

    def render_current_conversation(self):
        if not hasattr(self, "assistant_output"):
            return
        messages = []
        if self.current_conversation_id is not None:
            try:
                messages = self.conversation_manager.get_messages(self.current_conversation_id)
            except Exception:
                messages = []
        live_text = self.streaming_ai_responses.get(self.current_conversation_id, "")
        self.assistant_output.show_conversation(
            self.current_conversation_id, messages, live_text, self._thinking_active
        )
        self.refresh_assistant_metrics()

    def start_thinking_indicator(self, safe_command):
        self.thinking_command = self.thinking_command or safe_command
        self._thinking_active = True
        self.assistant_status.setText("● THINKING")
        self._set_orb_text(getattr(self.dashboard_core_widget, "state", "thinking"))
        self.render_current_conversation()

    def update_thinking_indicator(self):
        # The processing card is intentionally static; it does not delay or animate UI.
        if not self._thinking_active:
            self.thinking_timer.stop()

    def display_user_and_response(self, command, response):
        self._thinking_active = False
        self.thinking_timer.stop()
        self.render_current_conversation()
        self._schedule_data_refresh()

    def display_assistant_response(self, response):
        self._thinking_active = False
        self.thinking_timer.stop()
        self.render_current_conversation()
        self._schedule_data_refresh()

    # ========================================================
    # AI STREAMING + RESPONSE HANDLER
    # ========================================================

    def handle_ai_stream_chunk(self, conversation_id, text):
        """Append streamed text and refresh the visible conversation incrementally."""
        if not text:
            return
        self.streaming_ai_responses[conversation_id] = (
            self.streaming_ai_responses.get(conversation_id, "") + str(text)
        )
        if conversation_id == self.current_conversation_id:
            self.render_current_conversation()

    def handle_ai_speech_chunk(self, conversation_id, text, language="auto"):
        """Queue a completed phrase for speech while the local model keeps generating."""
        if not text or not self.voice_enabled or self.settings.legacy_openai_voice_enabled:
            return
        try:
            manager = self._ensure_speech_manager()
            if manager.enqueue(text, language):
                self.kokoro_streamed_conversations.add(conversation_id)
                self.voice_output_active = True
                if hasattr(self, "assistant_status"):
                    self.assistant_status.setText("● SPEAKING")
            elif not self._kokoro_unavailable_notified:
                self._kokoro_unavailable_notified = True
                self.add_activity("Voice output unavailable: " + (manager.last_error or "no speech engine found."))
        except Exception as error:  # noqa: BLE001
            if not self._kokoro_unavailable_notified:
                self._kokoro_unavailable_notified = True
                self.add_activity(f"Speech could not start: {error}")

    def handle_ai_response(
        self,
        conversation_id,
        message,
        response,
    ):

        self.pending_ai_requests = max(0, self.pending_ai_requests - 1)
        self.set_core_idle_state()

        conversation = (
            self.conversation_manager
            .get_conversation(
                conversation_id
            )
        )

        if not conversation:

            self.add_activity(
                "AI response received for "
                "a conversation that no longer exists."
            )

            self.refresh_conversation_list()

            return

        kokoro_spoke_this_response = conversation_id in self.kokoro_streamed_conversations
        self.kokoro_streamed_conversations.discard(conversation_id)
        self.streaming_ai_responses.pop(conversation_id, None)

        try:

            self.conversation_manager.add_message(
                conversation_id,
                "assistant",
                response,
            )

        except Exception as error:  # noqa: BLE001

            self.add_activity(
                "Could not save AI response: "
                f"{error}"
            )

            if (
                conversation_id
                == self.current_conversation_id
            ):

                self.thinking_timer.stop()
                self._thinking_active = False
                self.assistant_status.setText("● ERROR")
                self.render_current_conversation()

            return

        started = self.response_started_at.pop(conversation_id, None)
        if started is not None:
            elapsed = max(0.0, (__import__("datetime").datetime.now() - started).total_seconds())
            self.response_times.append(elapsed)
            self.response_times = self.response_times[-50:]
        self.ai_success_count += 1

        if (
            conversation_id
            == self.current_conversation_id
        ):

            self.thinking_timer.stop()
            self._thinking_active = False

            self.assistant_status.setText(
                "● READY"
            )

            self.render_current_conversation()

            self.add_activity(
                response
            )

            if getattr(
                self,
                "voice_enabled",
                False,
            ) and not kokoro_spoke_this_response:

                try:
                    response_language = self.ai_voice_languages.pop(
                        conversation_id,
                        self.current_voice_language,
                    )
                    self.speak_response(
                        response,
                        response_language,
                    )
                except Exception as error:  # noqa: BLE001

                    self.add_activity(
                        "Voice output error: "
                        f"{error}"
                    )

        self.ai_voice_languages.pop(
            conversation_id,
            None,
        )

        self.refresh_conversation_list()

    # ========================================================
    # AI ERROR HANDLER
    # ========================================================

    def handle_ai_error(
        self,
        conversation_id,
        message,
        error,
    ):

        error_message = "Nexus could not complete " "the request.\n\n" f"Error: {error}"
        self.streaming_ai_responses.pop(conversation_id, None)
        self.pending_ai_requests = max(0, self.pending_ai_requests - 1)
        self.set_core_idle_state()

        self.conversation_manager.add_message(
            conversation_id,
            "assistant",
            error_message,
        )

        started = self.response_started_at.pop(conversation_id, None)
        if started is not None:
            elapsed = max(0.0, (__import__("datetime").datetime.now() - started).total_seconds())
            self.response_times.append(elapsed)
            self.response_times = self.response_times[-50:]

        if conversation_id == self.current_conversation_id:

            self.thinking_timer.stop()
            self._thinking_active = False
            self.assistant_status.setText("● ERROR")
            self.render_current_conversation()
            self.add_activity(error_message)

        self.refresh_conversation_list()

    # ========================================================
    # CLEANUP AI WORKER
    # ========================================================

    def cleanup_ai_worker(
        self,
    ):

        sender = self.sender()

        if sender is None:
            return

        conversation_id = None

        for (
            cid,
            thread,
        ) in list(self.ai_threads.items()):

            if thread is sender:
                conversation_id = cid
                break

        if conversation_id is None:
            return

        thread = self.ai_threads.pop(
            conversation_id,
            None,
        )

        self.ai_workers.pop(
            conversation_id,
            None,
        )

        if thread:
            thread.deleteLater()

        self.refresh_conversation_list()

    # ========================================================
    # ACTIVITY
    # ========================================================

    def add_activity(
        self,
        text,
    ):

        from datetime import datetime

        self.activity_events.append(
            (
                datetime.now().strftime("%H:%M:%S"),  # noqa: DTZ005
                str(text),
            )
        )
        self.activity_events = self.activity_events[-60:]
        self.refresh_activity_view()
        self.refresh_dashboard_activity_feed()

    def refresh_activity_view(self):
        page = getattr(self, "activity_page", None)
        if page is not None:
            page.set_events(self.activity_events)

    def clear_assistant_chat(self):
        """Ctrl+L: start a clean conversation. Saved history is kept."""
        self.start_new_conversation()

    def clear_activity(self):
        self.activity_events.clear()
        self.refresh_activity_view()
        self.refresh_dashboard_activity_feed()

    # ========================================================
    # CONVERSATION CONTEXT MENU
    # ========================================================

    def show_conversation_context_menu(
        self,
        position,
    ):

        item = self.conversation_list.itemAt(position)

        if item is None:
            return

        conversation_id = item.data(Qt.UserRole)

        menu = QMenu(self)

        rename_action = menu.addAction("Rename")

        delete_action = menu.addAction("Delete")

        action = menu.exec(self.conversation_list.mapToGlobal(position))

        if action == rename_action:

            self.rename_conversation(conversation_id)

        elif action == delete_action:

            self.delete_conversation(conversation_id)

    # ========================================================
    # RENAME CONVERSATION
    # ========================================================

    def rename_conversation(
        self,
        conversation_id,
    ):

        conversation = self.conversation_manager.get_conversation(conversation_id)

        if not conversation:
            return

        title, ok = QInputDialog.getText(
            self,
            "Rename Conversation",
            "Conversation name:",
            text=conversation["title"],
        )

        if not ok:
            return

        title = title.strip()

        if not title:
            return

        self.conversation_manager.update_title(
            conversation_id,
            title,
        )

        self.refresh_conversation_list()

    # ========================================================
    # DELETE CONVERSATION
    # ========================================================

    def delete_conversation(
        self,
        conversation_id,
    ):

        conversation = self.conversation_manager.get_conversation(conversation_id)

        if not conversation:
            return

        reply = QMessageBox.question(
            self,
            "Delete conversation",
            ("Delete this conversation? This cannot be undone.\n\n" f"{conversation['title']}"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        self.conversation_manager.delete_conversation(conversation_id)

        if self.current_conversation_id == conversation_id:

            self.current_conversation_id = None

            self._thinking_active = False
            self.render_current_conversation()

        self.refresh_conversation_list()
        self.show_toast("Conversation deleted.")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "sidebar") and self._sidebar_collapsed is not None:
            self._apply_sidebar_mode()
        central_widget = self.centralWidget()
        if central_widget is not None and getattr(self, "system_check_overlay", None) is not None:
            self.system_check_overlay.setGeometry(central_widget.rect())
        toast = getattr(self, "toast", None)
        if toast is not None and toast.isVisible():
            toast._place()
