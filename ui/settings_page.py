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
from core.gemini_engine import gemini_is_configured, set_gemini_api_key


class SettingsPage(QWidget):
    """Functional NEXUS settings page."""

    settingsSaved = Signal()
    resetRequested = Signal()

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
            "Typed-response speech also requires the explicit legacy OpenAI TTS option below. Gemini Live voice responses use Gemini audio independently.",
        ))

        self.legacy_openai_voice = QCheckBox("Allow legacy OpenAI background voice and TTS")
        layout.addWidget(self._row(
            "Legacy voice services",
            self.legacy_openai_voice,
            "Off by default. When enabled with an OpenAI key, background wake-word speech recognition and typed-response audio use OpenAI. The foreground microphone uses Gemini Live instead.",
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
        self.settings.start_with_windows = self.startup_enabled.isChecked()

        self.gemini_key_status.setText(
            "Gemini API key detected. Online mode is selected; compatible text requests and Gemini Live voice can use it."
            if gemini_is_configured()
            else "Gemini API key not configured. Paste it above, or set GEMINI_API_KEY."
        )

        self.settingsSaved.emit()

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
