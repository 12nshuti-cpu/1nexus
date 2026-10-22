"""First-run setup wizard.

Walks a new user through: what NEXUS can do -> choosing an AI mode (and entering
a key if needed) -> voice -> privacy and behaviour -> finish.

* Nothing is saved until the user presses **Finish**.
* Every "Test" button runs on a background thread, so the window never freezes.
* "Skip setup" keeps the safe defaults and does not ask again.
"""
from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import NEXUSSettings
from core import connection_tests
from core import startup as startup_module
from core.gemini_engine import gemini_is_configured, set_gemini_api_key

STEP_TITLES = ("Welcome", "AI engine", "Voice", "Privacy & behaviour", "All set")


class _Runner(QObject):
    """Runs a blocking callable off the UI thread and reports back on it."""

    done = Signal(object)

    def run(self, work: Callable[[], object]) -> None:
        def target():
            try:
                result = work()
            except Exception as error:  # noqa: BLE001 - surfaced to the user, never raised on a thread
                result = connection_tests.Outcome(False, f"The test could not run: {error}")
            self.done.emit(result)

        threading.Thread(target=target, name="NEXUS-Wizard-Test", daemon=True).start()


class FirstRunWizard(QDialog):
    """Modal first-run setup."""

    def __init__(self, settings: NEXUSSettings | None = None, parent=None, speech_factory: Callable | None = None):
        super().__init__(parent)
        self.settings = settings or NEXUSSettings()
        self._speech_factory = speech_factory
        self._speech = None
        self.skipped = False
        self.last_warnings: list[str] = []
        self.setWindowTitle("Welcome to NEXUS")
        self.setModal(True)
        self.setMinimumSize(640, 520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 18)
        outer.setSpacing(12)

        self.step_label = QLabel()
        self.step_label.setObjectName("mutedText")
        outer.addWidget(self.step_label)
        self.title_label = QLabel()
        self.title_label.setObjectName("pageTitle")
        outer.addWidget(self.title_label)

        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        for builder in (self._page_welcome, self._page_ai, self._page_voice, self._page_privacy, self._page_finish):
            self.pages.addWidget(builder())

        nav = QHBoxLayout()
        self.skip_button = QPushButton("Skip setup")
        self.skip_button.setObjectName("secondaryButton")
        self.skip_button.clicked.connect(self.skip)
        nav.addWidget(self.skip_button)
        nav.addStretch()
        self.back_button = QPushButton("Back")
        self.back_button.setObjectName("secondaryButton")
        self.back_button.clicked.connect(self.back)
        nav.addWidget(self.back_button)
        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("primaryButton")
        self.next_button.clicked.connect(self.next)
        nav.addWidget(self.next_button)
        outer.addLayout(nav)

        self._runners: list[_Runner] = []
        self._go(0)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _label(text: str, muted: bool = False) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.PlainText)
        if muted:
            label.setObjectName("mutedText")
        return label

    def _run_test(self, work: Callable[[], object], button: QPushButton, status: QLabel) -> None:
        button.setEnabled(False)
        status.setText("Testing...")
        runner = _Runner(self)
        self._runners.append(runner)

        def finished(outcome):
            button.setEnabled(True)
            status.setText(("OK: " if outcome.ok else "Problem: ") + outcome.message)

        runner.done.connect(finished)
        runner.run(work)

    # -------------------------------------------------------------------- pages
    def _page_welcome(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._label(
            "NEXUS is your personal desktop assistant. It can chat by text or voice, keep reminders, "
            "remember things you ask it to, do quick calculations and conversions, and run approved "
            "Windows tasks - always telling you honestly what actually happened."
        ))
        layout.addWidget(self._label(
            "What needs the internet: online AI (Gemini) and Gemini Live voice. What works offline: local AI "
            "(if Ollama and a model are installed), reminders, memory, the clock, calculator and unit conversion."
        ))
        self.name_edit = QLineEdit(str(self.settings.get("user_name", "") or ""))
        self.name_edit.setPlaceholderText("What should NEXUS call you? (optional)")
        self.name_edit.setMaxLength(60)
        layout.addWidget(self.name_edit)
        layout.addStretch()
        return page

    def _page_ai(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._label("Choose how NEXUS thinks. You can change this at any time in Settings."))

        self.mode_group = QButtonGroup(self)
        self.mode_buttons: dict[str, QRadioButton] = {}
        for key, text, note in (
            ("automatic", "Automatic (recommended)",
             "Everyday chat and PC tasks stay local; harder questions use Gemini only if you add a key."),
            ("local", "Local only", "Nothing is sent to the cloud. Needs Ollama and a model installed."),
            ("online", "Online (Gemini)", "Best answers. Needs an internet connection and a Gemini API key."),
        ):
            button = QRadioButton(text)
            self.mode_group.addButton(button)
            self.mode_buttons[key] = button
            layout.addWidget(button)
            layout.addWidget(self._label(note, muted=True))
        self.mode_buttons[self.settings.ai_engine].setChecked(True)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Gemini API key (stored in the Windows Credential Manager)")
        self.key_edit.setClearButtonEnabled(True)
        layout.addWidget(self.key_edit)
        self.key_state = self._label(
            "A Gemini key is already saved." if gemini_is_configured() else "No Gemini key saved yet.", muted=True
        )
        layout.addWidget(self.key_state)

        row = QHBoxLayout()
        self.test_local_button = QPushButton("Test local AI")
        self.test_local_button.setObjectName("secondaryButton")
        self.test_online_button = QPushButton("Test Gemini")
        self.test_online_button.setObjectName("secondaryButton")
        row.addWidget(self.test_local_button)
        row.addWidget(self.test_online_button)
        row.addStretch()
        layout.addLayout(row)
        self.ai_status = self._label("", muted=True)
        layout.addWidget(self.ai_status)
        self.test_local_button.clicked.connect(
            lambda: self._run_test(lambda: connection_tests.check_ollama(self.settings), self.test_local_button, self.ai_status)
        )
        self.test_online_button.clicked.connect(self._test_gemini)
        layout.addStretch()
        return page

    def _test_gemini(self) -> None:
        # Save the key first (only on an explicit test click) so the test uses it.
        text = self.key_edit.text().strip()
        if text:
            try:
                set_gemini_api_key(text)
            except (OSError, ValueError) as error:
                self.ai_status.setText(f"Problem: could not save the key: {error}")
                return
            self.key_edit.clear()
            self.key_state.setText("A Gemini key is saved.")
        self._run_test(lambda: connection_tests.check_gemini(self.settings), self.test_online_button, self.ai_status)

    def _page_voice(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.voice_check = QCheckBox("Speak NEXUS's replies aloud")
        self.voice_check.setChecked(self.settings.voice_enabled)
        layout.addWidget(self.voice_check)
        layout.addWidget(self._label(
            "Automatic uses a natural, human-sounding voice when you are online (Microsoft's neural voices: the "
            "text being spoken is sent to Microsoft), Kokoro if you have installed it (see the Voice guide), and "
            "the built-in Windows voice otherwise. You will be told whenever NEXUS switches voices.", muted=True))
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Automatic (natural voice, then Kokoro, then Windows voice)", "auto")
        self.engine_combo.addItem("Natural voice only (online)", "natural")
        self.engine_combo.addItem("Kokoro only", "kokoro")
        self.engine_combo.addItem("Windows voice only", "windows")
        index = self.engine_combo.findData(self.settings.tts_engine)
        self.engine_combo.setCurrentIndex(max(0, index))
        layout.addWidget(self.engine_combo)

        row = QHBoxLayout()
        self.test_voice_button = QPushButton("Test voice")
        self.test_voice_button.setObjectName("secondaryButton")
        self.test_voice_button.clicked.connect(self._test_voice)
        self.test_mic_button = QPushButton("Check microphone")
        self.test_mic_button.setObjectName("secondaryButton")
        self.test_mic_button.clicked.connect(
            lambda: self._run_test(connection_tests.check_microphone, self.test_mic_button, self.voice_status)
        )
        row.addWidget(self.test_voice_button)
        row.addWidget(self.test_mic_button)
        row.addStretch()
        layout.addLayout(row)
        self.voice_status = self._label("", muted=True)
        layout.addWidget(self.voice_status)
        layout.addWidget(self._label(
            "Microphone use is always visible and only starts when you press the microphone button. "
            "NEXUS does not listen in the background unless you turn that on yourself.", muted=True))
        layout.addStretch()
        return page

    def _test_voice(self) -> None:
        # Apply the chosen engine temporarily to a private manager so the test reflects the choice.
        try:
            if self._speech is None:
                if self._speech_factory is not None:
                    self._speech = self._speech_factory(self.settings)
                else:
                    from core.speech import SpeechManager

                    self._speech = SpeechManager(self.settings)
            self.settings.tts_engine = self.engine_combo.currentData() or "auto"
            ok = self._speech.enqueue("Hello, I'm NEXUS. If you can hear this, voice is working.", "en")
            if ok:
                self.voice_status.setText("Playing a test phrase...")
            else:
                self.voice_status.setText("Problem: " + (self._speech.last_error or "No speech engine is available."))
        except Exception as error:  # noqa: BLE001
            self.voice_status.setText(f"Problem: voice test failed: {error}")

    def _page_privacy(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._label(
            "NEXUS only remembers what you explicitly ask it to remember, and stores it on this PC. "
            "You can view, edit, delete and export it at any time."))
        self.personalization_check = QCheckBox("Enable memory and personalization")
        self.personalization_check.setChecked(self.settings.personalization_enabled)
        self.share_check = QCheckBox("Include saved memories in online AI requests (off = stay on this PC)")
        self.share_check.setChecked(self.settings.share_memory_with_online)
        self.greeting_check = QCheckBox("Greet me when NEXUS starts")
        self.greeting_check.setChecked(self.settings.startup_greeting)
        self.tray_check = QCheckBox("Keep running in the system tray when I close the window (needed for reminders)")
        self.tray_check.setChecked(self.settings.close_to_tray)
        self.startup_check = QCheckBox("Start NEXUS when I sign in to Windows")
        self.startup_check.setChecked(self.settings.start_with_windows)
        for widget in (self.personalization_check, self.share_check, self.greeting_check, self.tray_check, self.startup_check):
            layout.addWidget(widget)
        layout.addStretch()
        return page

    def _page_finish(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.summary_label = self._label("")
        layout.addWidget(self.summary_label)
        layout.addWidget(self._label(
            "Try: \"what time is it\", \"remind me to stretch in 10 minutes\", \"remember that I like green tea\", "
            "\"convert 5 km to miles\". Open Settings any time to change what you chose here.", muted=True))
        layout.addStretch()
        return page

    # ---------------------------------------------------------------- navigation
    def _go(self, index: int) -> None:
        index = max(0, min(self.pages.count() - 1, index))
        self.pages.setCurrentIndex(index)
        self.step_label.setText(f"Step {index + 1} of {self.pages.count()}")
        self.title_label.setText(STEP_TITLES[index])
        self.back_button.setEnabled(index > 0)
        last = index == self.pages.count() - 1
        self.next_button.setText("Finish" if last else "Next")
        self.skip_button.setVisible(not last)
        if last:
            self.summary_label.setText(self.summary())

    def next(self) -> None:
        if self.pages.currentIndex() == self.pages.count() - 1:
            self.finish()
        else:
            self._go(self.pages.currentIndex() + 1)

    def back(self) -> None:
        self._go(self.pages.currentIndex() - 1)

    # -------------------------------------------------------------------- results
    def chosen_mode(self) -> str:
        for key, button in self.mode_buttons.items():
            if button.isChecked():
                return key
        return "automatic"

    def summary(self) -> str:
        mode = {"automatic": "Automatic", "local": "Local only", "online": "Online (Gemini)"}[self.chosen_mode()]
        key = "saved" if gemini_is_configured() or self.key_edit.text().strip() else "not set"
        lines = [
            f"AI engine: {mode} (Gemini key {key})",
            f"Spoken replies: {'on' if self.voice_check.isChecked() else 'off'}",
            f"Memory & personalization: {'on' if self.personalization_check.isChecked() else 'off'}",
            f"Run in tray: {'yes' if self.tray_check.isChecked() else 'no'}  |  Start with Windows: {'yes' if self.startup_check.isChecked() else 'no'}",
        ]
        if self.chosen_mode() == "online" and key == "not set":
            lines.append("Online mode needs a Gemini key - NEXUS will use Automatic until you add one in Settings.")
        return "\n".join(lines)

    def apply(self) -> list[str]:
        """Write the chosen options to settings. Returns human-readable warnings."""
        warnings: list[str] = []
        s = self.settings
        mode = self.chosen_mode()

        typed_key = self.key_edit.text().strip()
        if typed_key:
            try:
                set_gemini_api_key(typed_key)
                self.key_edit.clear()
            except (OSError, ValueError) as error:
                warnings.append(f"Your Gemini key could not be saved: {error}")
        if mode == "online" and not gemini_is_configured():
            warnings.append("Online mode needs a Gemini key, so NEXUS will use Automatic until you add one in Settings.")
            mode = "automatic"

        s.ai_engine = mode
        s.set("user_name", self.name_edit.text().strip()[:60])
        s.voice_enabled = self.voice_check.isChecked()
        s.tts_engine = self.engine_combo.currentData() or "auto"
        s.personalization_enabled = self.personalization_check.isChecked()
        s.share_memory_with_online = self.share_check.isChecked()
        s.startup_greeting = self.greeting_check.isChecked()
        s.close_to_tray = self.tray_check.isChecked()

        wanted = self.startup_check.isChecked()
        try:
            if startup_module.is_enabled() != wanted:
                startup_module.set_enabled(wanted)
        except startup_module.StartupError as error:
            if wanted:
                warnings.append(f"'Start with Windows' could not be enabled: {error}")
                wanted = False
        s.start_with_windows = wanted

        s.first_run_completed = True
        return warnings

    def finish(self) -> None:
        self.last_warnings = self.apply()
        self.accept()

    def skip(self) -> None:
        self.skipped = True
        self.settings.first_run_completed = True
        self.reject()

    def done(self, result: int) -> None:  # noqa: D401 - Qt override
        if self._speech is not None:
            try:
                self._speech.close()
            except Exception:  # noqa: BLE001
                pass
            self._speech = None
        super().done(result)
