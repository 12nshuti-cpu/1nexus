from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config.settings import NEXUSSettings
from core import startup as startup_module
from core.gemini_engine import gemini_is_configured, set_gemini_api_key
from core.speech import ENGLISH_VOICES


class SettingsPage(QWidget):
    """Functional NEXUS settings page."""

    settingsSaved = Signal()
    resetRequested = Signal()
    manageDataRequested = Signal()

    def __init__(self, settings: NEXUSSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._build()
        self.load_settings()

    def _section(self, title: str, subtitle: str):
        frame = QFrame()
        frame.setObjectName("dashboardPanel")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("mutedText")
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

        return frame, layout

    @staticmethod
    def _row(label: str, widget: QWidget, description: str = ""):
        row = QFrame()
        row.setObjectName("settingsRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(4)

        top = QHBoxLayout()
        text = QLabel(label)
        text.setObjectName("cardTitle")
        top.addWidget(text)
        top.addStretch()
        top.addWidget(widget)
        layout.addLayout(top)

        if description:
            note = QLabel(description)
            note.setObjectName("mutedText")
            note.setWordWrap(True)
            layout.addWidget(note)

        return row

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        header = QFrame()
        header.setObjectName("dashboardPanel")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)

        title = QLabel("NEXUS SETTINGS")
        title.setObjectName("pageTitle")
        header_layout.addWidget(title)

        subtitle = QLabel("Control how NEXUS uses your PC, AI model, voice, and Windows startup.")
        subtitle.setObjectName("mutedText")
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        # PC / shell execution
        section, layout = self._section(
            "PC CONTROL & SHELL",
            "Explicit shell requests such as 'run ipconfig' or 'powershell Get-Process' are executed locally.",
        )

        self.execution_enabled = QCheckBox("Enable shell command execution")
        layout.addWidget(self._row(
            "Execution",
            self.execution_enabled,
            "Controls direct Windows command execution and the AI-to-Windows tool.",
        ))

        self.ai_tool_execution = QCheckBox("Allow NEXUS AI to use Windows tools")
        layout.addWidget(self._row(
            "AI tool execution",
            self.ai_tool_execution,
            "When enabled, NEXUS can request a Windows command to inspect or act on real PC state, then use the result in its answer.",
        ))

        self.shell_combo = QComboBox()
        self.shell_combo.addItem("PowerShell", "powershell")
        self.shell_combo.addItem("Command Prompt", "cmd")
        self.shell_combo.setMinimumWidth(170)
        layout.addWidget(self._row(
            "Default shell",
            self.shell_combo,
            "The default shell for 'run', 'execute', 'terminal', and 'shell' requests.",
        ))

        self.confirm_risky = QCheckBox("Ask before risky commands")
        layout.addWidget(self._row(
            "Command confirmation",
            self.confirm_risky,
            "Commands that can remove files, change boot/security settings, stop processes, or shut down Windows prompt first.",
        ))

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 600)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setMinimumWidth(120)
        layout.addWidget(self._row(
            "Execution timeout",
            self.timeout_spin,
            "A command that runs longer than this is terminated by NEXUS.",
        ))

        directory_row = QFrame()
        directory_layout = QVBoxLayout(directory_row)
        directory_layout.setContentsMargins(0, 6, 0, 6)
        directory_layout.setSpacing(6)
        directory_title = QLabel("Working directory")
        directory_title.setObjectName("cardTitle")
        directory_layout.addWidget(directory_title)

        path_line = QHBoxLayout()
        self.working_directory = QLineEdit()
        self.working_directory.setPlaceholderText(str(Path.home()))
        path_line.addWidget(self.working_directory, 1)

        browse = QPushButton("Browse")
        browse.setObjectName("secondaryButton")
        browse.clicked.connect(self.browse_directory)
        path_line.addWidget(browse)
        directory_layout.addLayout(path_line)

        note = QLabel("Commands start in this directory unless the command itself changes location.")
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        directory_layout.addWidget(note)
        layout.addWidget(directory_row)

        content_layout.addWidget(section)

        # AI settings
        section, layout = self._section(
            "LOCAL AI",
            "Choose the Ollama model NEXUS uses for normal conversations.",
        )

        self.ai_model = QLineEdit()
        self.ai_model.setMinimumWidth(240)
        layout.addWidget(self._row(
            "Ollama model",
            self.ai_model,
            "Example: llama3.1:8b or your custom NEXUS Ollama model name.",
        ))

        self.ai_engine = QComboBox()
        self.ai_engine.addItem("Automatic (local-first; Gemini for selected complex tasks)", "automatic")
        self.ai_engine.addItem("Online (Gemini; local fallback if enabled)", "online")
        self.ai_engine.addItem("Local only (Ollama; no cloud prompts)", "local")
        self.ai_engine.setMinimumWidth(300)
        layout.addWidget(self._row(
            "AI engine",
            self.ai_engine,
            "Automatic keeps everyday and Windows-tool tasks local. Online requires a Gemini API key. Voice uses Gemini Live only when the key and connection are available.",
        ))

        self.gemini_model = QLineEdit()
        self.gemini_model.setMinimumWidth(240)
        layout.addWidget(self._row(
            "Gemini text model",
            self.gemini_model,
            "Cloud model used only for requests routed to Gemini. The Live voice model is managed separately.",
        ))

        self.online_fallback = QCheckBox("Fall back to local NEXUS if Gemini fails")
        layout.addWidget(self._row(
            "Online fallback",
            self.online_fallback,
            "When enabled, an unavailable/rate-limited Gemini request is retried locally and labeled as a local answer.",
        ))

        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setPlaceholderText("Paste your Gemini API key here")
        self.gemini_key_input.setEchoMode(QLineEdit.Password)
        self.gemini_key_input.setMinimumWidth(280)
        self.gemini_key_input.setClearButtonEnabled(True)
        layout.addWidget(self._row(
            "Gemini API key",
            self.gemini_key_input,
            "Paste the key and choose Save key & use Gemini. It is stored locally for your Windows user, never shown again, and is not added to chats or logs.",
        ))

        use_gemini = QPushButton("Save key & use Gemini")
        use_gemini.setObjectName("primaryButton")
        use_gemini.clicked.connect(self.save_gemini_and_enable_online)
        layout.addWidget(use_gemini)

        key_state = "Gemini API key detected. Choose Online to route compatible text requests to Gemini." if gemini_is_configured() else "Gemini API key not configured. Paste it above, or set GEMINI_API_KEY."
        self.gemini_key_status = QLabel(key_state)
        self.gemini_key_status.setObjectName("mutedText")
        self.gemini_key_status.setWordWrap(True)
        layout.addWidget(self.gemini_key_status)
        content_layout.addWidget(section)

        # Voice / startup
        section, layout = self._section(
            "VOICE & STARTUP",
            "Persist voice preferences and whether NEXUS should launch with Windows.",
        )

        self.voice_enabled = QCheckBox("Enable speech output")
        layout.addWidget(self._row(
            "Voice output",
            self.voice_enabled,
            "NEXUS reads its replies aloud (Kokoro or the Windows voice, see Speech output). Gemini Live voice turns use Gemini's own audio.",
        ))

        self.legacy_openai_voice = QCheckBox("Allow legacy OpenAI background voice and TTS")
        layout.addWidget(self._row(
            "Legacy voice services",
            self.legacy_openai_voice,
            "Off by default. When enabled with an OpenAI key, background wake-word listening and typed-response audio use OpenAI (cloud). Not needed for normal use.",
        ))

        self.voice_language = QComboBox()
        for code, label in (
            ("auto", "Automatic"),
            ("en", "English"),
            ("fr", "French"),
            ("sw", "Swahili"),
            ("es", "Spanish"),
            ("de", "German"),
            ("it", "Italian"),
            ("pt", "Portuguese"),
            ("rw", "Kinyarwanda"),
        ):
            self.voice_language.addItem(label, code)
        self.voice_language.setMinimumWidth(170)
        layout.addWidget(self._row(
            "Voice language",
            self.voice_language,
            "Used as the persisted default when voice mode is enabled.",
        ))

        self.startup_enabled = QCheckBox("Start NEXUS with Windows")
        layout.addWidget(self._row(
            "Windows startup",
            self.startup_enabled,
            "NEXUS will register itself for the current Windows user. Windows security/UAC behavior is unchanged.",
        ))
        content_layout.addWidget(section)

        # Speech input (local recognition)
        section, layout = self._section(
            "SPEECH INPUT",
            "The microphone button records only when you press it. In Local mode (or Automatic without a Gemini key) "
            "your speech is turned into text on this PC with Whisper; the audio is not saved or uploaded.",
        )
        self.microphone = QComboBox()
        self.microphone.addItem("System default", None)
        # The device list is filled in the first time this page is shown (see showEvent): asking the
        # audio drivers while the window is still being built can stall start-up on some PCs.
        self._microphones_loaded = False
        self.microphone.setMinimumWidth(260)
        layout.addWidget(self._row("Microphone", self.microphone, "Pick a specific input device, or leave on the system default."))
        self.stt_model = QComboBox()
        for code, label in (
            ("tiny", "Tiny - fastest, least accurate (~75 MB)"),
            ("base", "Base - balanced, multilingual (~145 MB)"),
            ("small", "Small - most accurate, slower (~480 MB)"),
            ("tiny.en", "Tiny, English only"),
            ("base.en", "Base, English only"),
            ("small.en", "Small, English only"),
        ):
            self.stt_model.addItem(label, code)
        self.stt_model.setMinimumWidth(260)
        layout.addWidget(self._row("Recognition model", self.stt_model,
                                   "Downloaded once on first use (internet needed that one time), then works offline."))
        self.push_to_talk = QCheckBox("Push-to-talk")
        layout.addWidget(self._row(
            "Listening mode",
            self.push_to_talk,
            "Off: NEXUS stops listening when you pause. On: click the microphone to start and click again when you are done.",
        ))
        content_layout.addWidget(section)

        # Speech output engine
        section, layout = self._section(
            "SPEECH OUTPUT",
            "NEXUS speaks with Kokoro when it is installed and falls back to the Windows voice if it is not or if it fails. "
            "You are told when the fallback voice is used.",
        )
        self.tts_engine = QComboBox()
        self.tts_engine.addItem("Automatic (Kokoro, then Windows voice)", "auto")
        self.tts_engine.addItem("Kokoro only", "kokoro")
        self.tts_engine.addItem("Windows voice only", "windows")
        self.tts_engine.setMinimumWidth(260)
        layout.addWidget(self._row("Speech engine", self.tts_engine,
                                   "Kokoro is installed separately (see the Voice guide); it runs in its own helper process."))
        self.kokoro_voice = QComboBox()
        for voice in ENGLISH_VOICES:
            self.kokoro_voice.addItem(voice, voice)
        self.kokoro_voice.setMinimumWidth(170)
        layout.addWidget(self._row("Kokoro voice", self.kokoro_voice, "Used for English replies."))
        self.kokoro_speed = QDoubleSpinBox()
        self.kokoro_speed.setRange(0.5, 2.0)
        self.kokoro_speed.setSingleStep(0.1)
        self.kokoro_speed.setDecimals(1)
        self.kokoro_speed.setMinimumWidth(100)
        layout.addWidget(self._row("Speech speed", self.kokoro_speed, "1.0 is normal speed."))
        content_layout.addWidget(section)

        # Personalization & privacy
        section, layout = self._section(
            "PRIVACY & PERSONALIZATION",
            "NEXUS only remembers what you explicitly ask it to remember. Everything is stored on this PC.",
        )
        self.user_name = QLineEdit()
        self.user_name.setMinimumWidth(200)
        self.user_name.setPlaceholderText("Optional")
        layout.addWidget(self._row("Your name", self.user_name, "Used in greetings only."))
        self.personalization = QCheckBox("Enable memory and personalization")
        layout.addWidget(self._row(
            "Personalization", self.personalization,
            "When off, NEXUS neither saves nor uses memories. Existing memories are kept until you delete them.",
        ))
        self.share_memory = QCheckBox("Include saved memories in online (Gemini) requests")
        layout.addWidget(self._row(
            "Share memory with online AI", self.share_memory,
            "Off by default. Saved memories stay on this PC and are never sent to a cloud service unless you enable this.",
        ))
        manage = QPushButton("Manage reminders, memories && data...")
        manage.setObjectName("secondaryButton")
        manage.clicked.connect(self.manageDataRequested.emit)
        layout.addWidget(manage)
        content_layout.addWidget(section)

        # Reminders & window behaviour
        section, layout = self._section(
            "REMINDERS & WINDOW",
            "Reminders notify you while NEXUS is running, including when it is minimised to the system tray.",
        )
        self.reminder_notifications = QCheckBox("Show a notification when a reminder is due")
        layout.addWidget(self._row("Reminder notifications", self.reminder_notifications))
        self.speak_reminders = QCheckBox("Speak reminders aloud (needs speech output enabled)")
        layout.addWidget(self._row("Spoken reminders", self.speak_reminders))
        self.startup_greeting = QCheckBox("Greet me when NEXUS starts")
        layout.addWidget(self._row("Startup greeting", self.startup_greeting,
                                   "Uses your real local date and time. It is spoken only if speech output is enabled."))
        self.close_to_tray = QCheckBox("Keep running in the system tray when the window is closed")
        layout.addWidget(self._row("Close to tray", self.close_to_tray,
                                   "Needed for reminders to keep notifying you after you close the window. Use Exit in the tray menu to quit."))
        self.start_minimized = QCheckBox("Start minimised to the tray")
        layout.addWidget(self._row("Start minimised", self.start_minimized))
        self.global_hotkey = QCheckBox("Enable the Ctrl+Alt+N shortcut (runs a small helper in the background)")
        layout.addWidget(self._row(
            "Global shortcut", self.global_hotkey,
            "Off by default. When on, a tiny helper program stays running to open NEXUS with Ctrl+Alt+N, even after "
            "NEXUS is closed. Takes effect the next time NEXUS starts.",
        ))
        content_layout.addWidget(section)

        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()

        reset = QPushButton("Reset")
        reset.setObjectName("secondaryButton")
        reset.clicked.connect(self.reset_settings)
        buttons.addWidget(reset)

        save = QPushButton("Save settings")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save_settings)
        buttons.addWidget(save)
        outer.addLayout(buttons)

    def browse_directory(self):
        current = self.working_directory.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Choose command working directory", current)
        if selected:
            self.working_directory.setText(selected)

    def save_gemini_and_enable_online(self):
        """Save the entered credential and explicitly select Gemini Online."""
        if not self.gemini_key_input.text().strip() and not gemini_is_configured():
            QMessageBox.warning(self, "Gemini key required", "Paste your Gemini API key first.")
            return
        online_index = self.ai_engine.findData("online")
        if online_index >= 0:
            self.ai_engine.setCurrentIndex(online_index)
        self.save_settings()

    def showEvent(self, event):  # noqa: N802 - Qt override
        super().showEvent(event)
        self._load_microphones()

    def _load_microphones(self):
        """Fill the microphone list once, keeping the saved choice selected."""
        if self._microphones_loaded:
            return
        self._microphones_loaded = True
        try:
            from core.stt import list_input_devices

            devices = list_input_devices()
        except Exception:  # noqa: BLE001 - listing devices must never break Settings
            devices = []
        saved = self.settings.microphone_device
        for index, name in devices:
            self.microphone.addItem(f"{name} (#{index})", index)
        if saved is not None and self.microphone.findData(saved) < 0:
            self.microphone.addItem(f"Saved device (#{saved}) - not currently connected", saved)
        pick = self.microphone.findData(saved)
        self.microphone.setCurrentIndex(pick if pick >= 0 else 0)

    def load_settings(self):
        self.execution_enabled.setChecked(self.settings.execution_enabled)

        shell_index = self.shell_combo.findData(self.settings.shell)
        if shell_index >= 0:
            self.shell_combo.setCurrentIndex(shell_index)

        self.confirm_risky.setChecked(self.settings.confirm_risky_commands)
        self.ai_tool_execution.setChecked(self.settings.ai_tool_execution_enabled)
        self.timeout_spin.setValue(self.settings.command_timeout)
        self.working_directory.setText(str(self.settings.working_directory))
        self.ai_model.setText(self.settings.ai_model)
        index = self.ai_engine.findData(self.settings.ai_engine)
        if index >= 0:
            self.ai_engine.setCurrentIndex(index)
        self.gemini_model.setText(self.settings.gemini_text_model)
        self.online_fallback.setChecked(self.settings.online_fallback_enabled)
        self.voice_enabled.setChecked(self.settings.voice_enabled)
        self.legacy_openai_voice.setChecked(self.settings.legacy_openai_voice_enabled)

        voice_index = self.voice_language.findData(self.settings.voice_language)
        if voice_index >= 0:
            self.voice_language.setCurrentIndex(voice_index)

        self.startup_enabled.setChecked(self.settings.start_with_windows)

        engine_index = self.tts_engine.findData(self.settings.tts_engine)
        if engine_index >= 0:
            self.tts_engine.setCurrentIndex(engine_index)
        voice_pick = self.kokoro_voice.findData(self.settings.kokoro_voice)
        if voice_pick >= 0:
            self.kokoro_voice.setCurrentIndex(voice_pick)
        self.kokoro_speed.setValue(self.settings.kokoro_speed)
        if self._microphones_loaded:
            mic_pick = self.microphone.findData(self.settings.microphone_device)
            self.microphone.setCurrentIndex(mic_pick if mic_pick >= 0 else 0)
        model_pick = self.stt_model.findData(self.settings.stt_model)
        if model_pick >= 0:
            self.stt_model.setCurrentIndex(model_pick)
        self.push_to_talk.setChecked(self.settings.push_to_talk)
        self.user_name.setText(str(self.settings.get("user_name", "") or ""))
        self.personalization.setChecked(self.settings.personalization_enabled)
        self.share_memory.setChecked(self.settings.share_memory_with_online)
        self.reminder_notifications.setChecked(self.settings.reminder_notifications)
        self.speak_reminders.setChecked(self.settings.speak_reminders)
        self.startup_greeting.setChecked(self.settings.startup_greeting)
        self.close_to_tray.setChecked(self.settings.close_to_tray)
        self.start_minimized.setChecked(self.settings.start_minimized)
        self.global_hotkey.setChecked(self.settings.global_hotkey_enabled)

    def _apply_windows_startup(self, wanted: bool) -> str:
        """Change the Windows sign-in entry. Returns an error message, or ``""`` on success."""
        try:
            current = startup_module.is_enabled()
        except startup_module.StartupError as error:
            # Not Windows: nothing to remove, so only complain if the user asked to turn it on.
            return str(error) if wanted else ""
        if current == wanted:
            return ""
        try:
            startup_module.set_enabled(wanted)
        except startup_module.StartupError as error:
            return str(error)
        return ""

    def save_settings(self):
        working = Path(self.working_directory.text().strip()).expanduser()
        if not working.exists() or not working.is_dir():
            QMessageBox.warning(
                self,
                "Invalid working directory",
                "Choose an existing folder before saving the settings.",
            )
            return

        model = self.ai_model.text().strip()
        if not model:
            QMessageBox.warning(self, "Invalid model", "Enter an Ollama model name.")
            return

        key = self.gemini_key_input.text().strip()
        if key:
            try:
                set_gemini_api_key(key)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Could not save Gemini key", str(error))
                return
            self.gemini_key_input.clear()
        elif self.ai_engine.currentData() == "online" and not gemini_is_configured():
            QMessageBox.warning(
                self,
                "Gemini key required",
                "Online mode needs a Gemini API key. Paste it above and choose Save key & use Gemini.",
            )
            return

        self.settings.execution_enabled = self.execution_enabled.isChecked()
        self.settings.ai_tool_execution_enabled = self.ai_tool_execution.isChecked()
        self.settings.shell = self.shell_combo.currentData() or "powershell"
        self.settings.confirm_risky_commands = self.confirm_risky.isChecked()
        self.settings.command_timeout = self.timeout_spin.value()
        self.settings.working_directory = working
        self.settings.ai_model = model
        self.settings.ai_engine = self.ai_engine.currentData() or "automatic"
        self.settings.gemini_text_model = self.gemini_model.text().strip()
        self.settings.online_fallback_enabled = self.online_fallback.isChecked()
        self.settings.voice_enabled = self.voice_enabled.isChecked()
        self.settings.legacy_openai_voice_enabled = self.legacy_openai_voice.isChecked()
        self.settings.voice_language = self.voice_language.currentData() or "auto"
        startup_error = self._apply_windows_startup(self.startup_enabled.isChecked())
        if startup_error:
            self.startup_enabled.setChecked(False)
        self.settings.start_with_windows = self.startup_enabled.isChecked()

        self.settings.tts_engine = self.tts_engine.currentData() or "auto"
        self.settings.kokoro_voice = self.kokoro_voice.currentData() or "af_heart"
        self.settings.kokoro_speed = self.kokoro_speed.value()
        if self._microphones_loaded:  # otherwise the page never listed devices; keep the stored choice
            self.settings.microphone_device = self.microphone.currentData()
        self.settings.stt_model = self.stt_model.currentData() or "base"
        self.settings.push_to_talk = self.push_to_talk.isChecked()
        self.settings.set("user_name", self.user_name.text().strip()[:60])
        self.settings.personalization_enabled = self.personalization.isChecked()
        self.settings.share_memory_with_online = self.share_memory.isChecked()
        self.settings.reminder_notifications = self.reminder_notifications.isChecked()
        self.settings.speak_reminders = self.speak_reminders.isChecked()
        self.settings.startup_greeting = self.startup_greeting.isChecked()
        self.settings.close_to_tray = self.close_to_tray.isChecked()
        self.settings.start_minimized = self.start_minimized.isChecked()
        self.settings.global_hotkey_enabled = self.global_hotkey.isChecked()

        self.gemini_key_status.setText(
            "Gemini API key detected. Online mode is selected; compatible text requests and Gemini Live voice can use it."
            if gemini_is_configured()
            else "Gemini API key not configured. Paste it above, or set GEMINI_API_KEY."
        )

        self.settingsSaved.emit()

        if startup_error:
            QMessageBox.warning(
                self,
                "Settings saved - with one problem",
                "Your settings were saved, but 'Start NEXUS with Windows' could not be changed:\n\n" + startup_error,
            )
            return
        QMessageBox.information(
            self,
            "Settings saved",
            "NEXUS settings have been saved and the active configuration has been updated.",
        )

    def reset_settings(self):
        choice = QMessageBox.question(
            self,
            "Reset NEXUS settings",
            "Reset all NEXUS application settings to their defaults?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if choice != QMessageBox.Yes:
            return

        self.settings.reset()
        self.load_settings()
        self.resetRequested.emit()
