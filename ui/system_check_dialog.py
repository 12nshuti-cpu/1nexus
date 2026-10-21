from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class SystemCheckDialog(QFrame):
    """Fast in-app startup diagnostics overlay for NEXUS.

    Uses only Qt widgets/styles. There is deliberately no custom paintEvent or
    animation, preventing QPainter re-entry warnings and keeping startup fast.
    """

    continueRequested = Signal()
    retryRequested = Signal()
    fixRequested = Signal(int)

    def __init__(self, results=None, parent=None):
        super().__init__(parent)
        self.results = list(results or [])
        self.setObjectName("systemCheckOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowFlags(Qt.Widget)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._build_ui()
        self.set_results(self.results)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setAlignment(Qt.AlignCenter)

        self.card = QFrame()
        self.card.setObjectName("systemCheckCard")
        self.card.setMinimumSize(620, 500)
        self.card.setMaximumWidth(760)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(34, 30, 34, 28)
        card_layout.setSpacing(14)

        top = QHBoxLayout()
        brand = QLabel("NEXUS")
        brand.setObjectName("systemBrand")
        top.addWidget(brand)
        top.addStretch()
        badge = QLabel("Start-up check")
        badge.setObjectName("systemBadge")
        top.addWidget(badge)
        card_layout.addLayout(top)

        title = QLabel("Getting NEXUS ready")
        title.setObjectName("systemTitle")
        card_layout.addWidget(title)

        self.status_label = QLabel("Initializing system checks…")
        self.status_label.setObjectName("systemStatus")
        self.status_label.setWordWrap(True)
        card_layout.addWidget(self.status_label)

        line = QFrame()
        line.setObjectName("systemLine")
        line.setFixedHeight(1)
        card_layout.addWidget(line)

        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("systemResultsScroll")
        scroll.setWidget(self.results_container)
        card_layout.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        self.hint = QLabel("Missing items can be fixed later from Settings; NEXUS never blocks you from starting.")
        self.hint.setObjectName("systemHint")
        self.hint.setWordWrap(True)
        bottom.addWidget(self.hint, 1)

        self.retry_button = QPushButton("Run checks again")
        self.retry_button.setObjectName("systemRetry")
        self.retry_button.setMinimumSize(130, 44)
        self.retry_button.clicked.connect(self.retryRequested.emit)
        self.retry_button.setVisible(False)
        bottom.addWidget(self.retry_button)

        self.continue_button = QPushButton("Continue to NEXUS  ›")
        self.continue_button.setObjectName("systemContinue")
        self.continue_button.setMinimumSize(190, 44)
        self.continue_button.clicked.connect(self._request_continue)
        self.continue_button.setEnabled(False)
        bottom.addWidget(self.continue_button)

        card_layout.addLayout(bottom)
        root.addWidget(self.card)

        # Colours come from the application theme (ui/theme.py).

    def update_status(self, text: str):
        self.status_label.setText(str(text))

    @staticmethod
    def _is_required(result):
        return bool(getattr(result, "required", True))

    def set_results(self, results):
        self.results = list(results or [])
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self.results:
            self.update_status("No diagnostic results were returned.")
            self.continue_button.setEnabled(False)
            self.retry_button.setVisible(False)
            return

        for index, result in enumerate(self.results):
            self.results_layout.addWidget(self._create_result_widget(result, index))
        self.results_layout.addStretch()

        required_failures = sum(
            1 for result in self.results
            if self._is_required(result) and not bool(getattr(result, "success", False))
        )
        optional_failures = sum(
            1 for result in self.results
            if not self._is_required(result) and not bool(getattr(result, "success", False))
        )

        if required_failures == 0:
            if optional_failures:
                self.update_status(
                    f"Startup requirements are ready. {optional_failures} optional check(s) still need attention."
                )
            else:
                self.update_status("System check complete — all required components are ready.")
        else:
            self.update_status(
                f"{required_failures} required component(s) need attention before NEXUS can continue."
            )

        # Never lock the user out: with a missing requirement they can still
        # use reminders, memory and tools, and fix the problem from Settings.
        self.continue_button.setEnabled(True)
        self.continue_button.setText("Continue anyway  ›" if required_failures else "Continue to NEXUS  ›")
        self.retry_button.setVisible(required_failures > 0)

    def _request_continue(self):
        self.continueRequested.emit()

    @staticmethod
    def _action_for_result(result):
        text = f"{getattr(result, 'name', '')} {getattr(result, 'details', '')}".lower()
        if "ollama" in text or "llama3.1:8b" in text:
            return "fix", "NEXUS can prepare the local AI requirement."
        if "microphone" in text:
            return "assist", "Open Windows microphone settings."
        return None, ""

    @classmethod
    def _can_auto_fix(cls, result):
        return cls._action_for_result(result)[0] == "fix"

    def set_busy(self, busy):
        self.continue_button.setEnabled(not busy and bool(self.results))
        self.retry_button.setEnabled(not busy)
        for button in self.findChildren(QPushButton, "systemFix"):
            button.setEnabled(not busy)

    def _create_result_widget(self, result, index):
        frame = QFrame()
        frame.setObjectName("checkFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(11)

        success = bool(getattr(result, "success", False))
        required = self._is_required(result)
        if success:
            symbol, status_name = "✓", "checkStatusGood"
        elif required:
            symbol, status_name = "!", "checkStatusBad"
        else:
            symbol, status_name = "~", "checkStatusOptional"

        status = QLabel(symbol)
        status.setObjectName(status_name)
        status.setFixedSize(34, 34)
        status.setAlignment(Qt.AlignCenter)
        layout.addWidget(status)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        name = QLabel(str(getattr(result, "name", "Check")))
        name.setObjectName("checkName")
        details = QLabel(str(getattr(result, "details", "")))
        details.setObjectName("checkDetails")
        details.setWordWrap(True)
        text_layout.addWidget(name)
        text_layout.addWidget(details)

        if not success:
            action, description = self._action_for_result(result)
            if action == "fix":
                action_text = description
            elif action == "assist":
                action_text = description
            else:
                action_text = "Complete this requirement, then run the check again."
            action_label = QLabel(action_text)
            action_label.setObjectName("checkAction")
            action_label.setWordWrap(True)
            text_layout.addWidget(action_label)

        layout.addLayout(text_layout, 1)

        if not success and required and self._can_auto_fix(result):
            fix_button = QPushButton("Fix automatically")
            fix_button.setObjectName("systemFix")
            fix_button.clicked.connect(lambda _checked=False, i=index: self.fixRequested.emit(i))
            layout.addWidget(fix_button)

        return frame
