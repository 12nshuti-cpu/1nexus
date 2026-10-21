"""Reminders, Memory and Activity screens.

These read and write the same stores the assistant uses (``core.reminders`` and
``core.memory``), so anything said in chat ("remind me to…", "remember that…") shows up
here and the other way round.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.components import Card, EmptyState, IconButton, IconLabel, repolish


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("pageTitle")
        text.addWidget(self.title)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        self.subtitle.setVisible(bool(subtitle))
        text.addWidget(self.subtitle)
        layout.addLayout(text, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)


def scroll_page(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    content.setObjectName("scrollContent")
    scroll.setWidget(content)
    return scroll


class _Page(QWidget):
    toast = Signal(str, str)

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        self.layout_ = QVBoxLayout(content)
        self.layout_.setContentsMargins(36, 28, 36, 28)
        self.layout_.setSpacing(18)
        self.header = PageHeader(title, subtitle)
        self.layout_.addWidget(self.header)
        outer.addWidget(scroll_page(content))

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # takeAt() already removed it from the layout; the parent stays until Qt
                # deletes it, so Python never destroys a widget in the middle of an update.
                widget.hide()
                widget.deleteLater()


def _row(icon_widget, title: str, meta: str = "", *, done=False, overdue=False):
    row = QFrame()
    row.setObjectName("listRow")
    row.setProperty("done", "true" if done else "false")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(10, 8, 6, 8)
    layout.setSpacing(12)
    layout.addWidget(icon_widget, 0, Qt.AlignTop)
    text = QVBoxLayout()
    text.setSpacing(2)
    label = QLabel(title)
    label.setObjectName("rowTitle")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    text.addWidget(label)
    if meta:
        meta_label = QLabel(meta)
        meta_label.setObjectName("rowMeta")
        meta_label.setProperty("overdue", "true" if overdue else "false")
        text.addWidget(meta_label)
    layout.addLayout(text, 1)
    repolish(row)
    return row, layout


# ============================================================================= reminders
class RemindersPage(_Page):
    changed = Signal()

    def __init__(self, store, parent=None):
        super().__init__("Reminders", "NEXUS notifies you when they are due, even from the system tray.", parent)
        self.store = store
        self.show_done = False

        add_card = Card()
        add_row = QHBoxLayout()
        add_row.setSpacing(10)
        add_row.addWidget(IconLabel("bell", 18, "accent"))
        self.input = QLineEdit()
        self.input.setPlaceholderText("Call Sam in 10 minutes  ·  Submit the form tomorrow at 9am")
        self.input.setAccessibleName("New reminder")
        self.input.returnPressed.connect(self.add_from_input)
        add_row.addWidget(self.input, 1)
        add = QPushButton("Add reminder")
        add.setObjectName("primaryButton")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self.add_from_input)
        add_row.addWidget(add)
        add_card.body.addLayout(add_row)
        self.feedback = QLabel("Write what to do and when. You can also just ask NEXUS in chat.")
        self.feedback.setObjectName("faintText")
        add_card.body.addWidget(self.feedback)
        self.layout_.addWidget(add_card)

        self.toggle_done = QPushButton("Show completed")
        self.toggle_done.setObjectName("ghostButton")
        self.toggle_done.setCursor(Qt.PointingHandCursor)
        self.toggle_done.clicked.connect(self._toggle_done)
        self.header.actions.addWidget(self.toggle_done)
        self.clear_done = QPushButton("Clear completed")
        self.clear_done.setObjectName("ghostButton")
        self.clear_done.setCursor(Qt.PointingHandCursor)
        self.clear_done.clicked.connect(self._clear_completed)
        self.header.actions.addWidget(self.clear_done)

        self.list_card = Card()
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(2)
        self.list_card.body.addLayout(self.list_layout)
        self.layout_.addWidget(self.list_card)
        self.layout_.addStretch(1)
        self.refresh()

    # ---- data
    def upcoming(self, limit: int = 4):
        try:
            return [r for r in self.store.list(include_done=False) if r.status != "done"][:limit]
        except Exception:  # noqa: BLE001
            return []

    def refresh(self):
        from core.timeparse import describe_due

        self._clear(self.list_layout)
        try:
            reminders = self.store.list(include_done=self.show_done)
        except Exception as error:  # noqa: BLE001
            self.list_layout.addWidget(EmptyState("alert", "Reminders could not be loaded", str(error)))
            return
        now = datetime.now()
        if not reminders:
            self.list_layout.addWidget(EmptyState(
                "bell", "No reminders yet",
                "Add one above, or say \"remind me to stretch in 30 minutes\" to NEXUS.",
            ))
            return
        pending = [r for r in reminders if r.status != "done"]
        done = [r for r in reminders if r.status == "done"]
        for title, group in (("Upcoming", pending), ("Completed", done)):
            if not group:
                continue
            label = QLabel(title.upper())
            label.setObjectName("sectionLabel")
            label.setContentsMargins(10, 8, 0, 4)
            self.list_layout.addWidget(label)
            for reminder in group:
                self.list_layout.addWidget(self._reminder_row(reminder, now, describe_due))

    def _reminder_row(self, reminder, now, describe_due):
        done = reminder.status == "done"
        overdue = not done and reminder.due_at < now
        complete = IconButton("check_circle" if done else "circle",
                              "Mark as not done" if done else "Mark as done",
                              size=30, icon_size=18, role="success" if done else "faint")
        complete.setEnabled(not done)
        complete.clicked.connect(lambda _=False, rid=reminder.id: self._complete(rid))
        when = describe_due(reminder.due_at, now)
        meta = ("Overdue · " if overdue else "") + when[0].upper() + when[1:]
        if reminder.status == "fired" and not overdue:
            meta += " · notified"
        row, layout = _row(complete, reminder.message, meta, done=done, overdue=overdue)
        if not done:
            reschedule = IconButton("clock", "Change time", size=30, icon_size=16)
            reschedule.clicked.connect(lambda _=False, r=reminder: self._reschedule(r))
            layout.addWidget(reschedule, 0, Qt.AlignVCenter)
            edit = IconButton("edit", "Edit text", size=30, icon_size=16)
            edit.clicked.connect(lambda _=False, r=reminder: self._edit(r))
            layout.addWidget(edit, 0, Qt.AlignVCenter)
        delete = IconButton("trash", "Delete reminder", size=30, icon_size=16)
        delete.clicked.connect(lambda _=False, r=reminder: self._delete(r))
        layout.addWidget(delete, 0, Qt.AlignVCenter)
        return row

    # ---- actions
    def add_from_input(self):
        from core.timeparse import describe_due, parse_reminder

        text = self.input.text().strip()
        if not text:
            self.input.setFocus()
            return
        lowered = text.lower()
        sentence = text if lowered.startswith(("remind me", "set a reminder", "reminder")) else "remind me to " + text
        parsed = parse_reminder(sentence)
        if parsed is None:
            self.feedback.setObjectName("errorText")
            self.feedback.setText("I couldn't work out when. Try \"… in 20 minutes\", \"… at 6pm\" or \"… tomorrow at 9am\".")
            repolish(self.feedback)
            return
        try:
            self.store.create(parsed.message, parsed.due)
        except ValueError as error:
            self.feedback.setObjectName("errorText")
            self.feedback.setText(str(error))
            repolish(self.feedback)
            return
        self.input.clear()
        self.feedback.setObjectName("faintText")
        self.feedback.setText("Write what to do and when. You can also just ask NEXUS in chat.")
        repolish(self.feedback)
        self.toast.emit(f"Reminder set for {describe_due(parsed.due)}.", "success")
        self.refresh()
        self.changed.emit()

    def _complete(self, reminder_id):
        try:
            self.store.complete(reminder_id)
        except ValueError as error:
            self.toast.emit(str(error), "error")
        self.refresh()
        self.changed.emit()

    def _reschedule(self, reminder):
        from core.timeparse import describe_due, parse_time

        text, ok = QInputDialog.getText(self, "Change time", f"New time for \"{reminder.message}\"\n(e.g. in 1 hour, tomorrow at 8am):")
        if not ok or not text.strip():
            return
        parsed = parse_time(text)
        if parsed is None:
            self.toast.emit("I couldn't understand that time.", "error")
            return
        try:
            self.store.update(reminder.id, None, parsed.due)
            self.toast.emit(f"Moved to {describe_due(parsed.due)}.", "success")
        except ValueError as error:
            self.toast.emit(str(error), "error")
        self.refresh()
        self.changed.emit()

    def _edit(self, reminder):
        text, ok = QInputDialog.getText(self, "Edit reminder", "Reminder:", text=reminder.message)
        if not ok or not text.strip():
            return
        try:
            self.store.update(reminder.id, text.strip(), None)
        except ValueError as error:
            self.toast.emit(str(error), "error")
        self.refresh()
        self.changed.emit()

    def _delete(self, reminder):
        if QMessageBox.question(self, "Delete reminder", f"Delete this reminder?\n\n{reminder.message}",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.store.delete(reminder.id)
            self.toast.emit("Reminder deleted.", "success")
        except ValueError as error:
            self.toast.emit(str(error), "error")
        self.refresh()
        self.changed.emit()

    def _toggle_done(self):
        self.show_done = not self.show_done
        self.toggle_done.setText("Hide completed" if self.show_done else "Show completed")
        self.refresh()

    def _clear_completed(self):
        try:
            removed = self.store.clear_completed()
        except Exception as error:  # noqa: BLE001
            self.toast.emit(str(error), "error")
            return
        self.toast.emit(f"Removed {removed} completed reminder{'s' if removed != 1 else ''}." if removed
                        else "There were no completed reminders.", "info")
        self.refresh()
        self.changed.emit()


# ============================================================================= memory
class MemoryPage(_Page):
    def __init__(self, store, settings, parent=None):
        super().__init__("Memory", "Facts NEXUS keeps about you to personalise answers. Stored only on this PC.", parent)
        self.store = store
        self.settings = settings

        self.status = QFrame()
        self.status.setObjectName("cardFlat")
        status_layout = QHBoxLayout(self.status)
        status_layout.setContentsMargins(14, 10, 14, 10)
        status_layout.setSpacing(10)
        self.status_icon = IconLabel("info", 17, "accent")
        status_layout.addWidget(self.status_icon)
        self.status_text = QLabel()
        self.status_text.setObjectName("mutedText")
        self.status_text.setWordWrap(True)
        status_layout.addWidget(self.status_text, 1)
        self.layout_.addWidget(self.status)

        add_card = Card()
        add_row = QHBoxLayout()
        add_row.setSpacing(10)
        add_row.addWidget(IconLabel("memory", 18, "accent"))
        self.input = QLineEdit()
        self.input.setPlaceholderText("My sister is called Aline  ·  I prefer short answers")
        self.input.setAccessibleName("New memory")
        self.input.returnPressed.connect(self.add_from_input)
        add_row.addWidget(self.input, 1)
        add = QPushButton("Remember")
        add.setObjectName("primaryButton")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self.add_from_input)
        add_row.addWidget(add)
        add_card.body.addLayout(add_row)
        self.layout_.addWidget(add_card)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search memories")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        self.search.textChanged.connect(self.refresh)
        self.header.actions.addWidget(self.search)
        clear = QPushButton("Forget all")
        clear.setObjectName("dangerButton")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self._clear_all)
        self.header.actions.addWidget(clear)

        self.list_card = Card()
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(2)
        self.list_card.body.addLayout(self.list_layout)
        self.layout_.addWidget(self.list_card)
        self.layout_.addStretch(1)
        self.refresh()

    def refresh(self, *_):
        enabled = bool(getattr(self.settings, "personalization_enabled", True))
        shared = bool(getattr(self.settings, "share_memory_with_online", False))
        if not enabled:
            self.status_text.setText("Personalisation is off, so NEXUS is not saving or using memories. "
                                     "Turn it on in Settings › Privacy.")
            self.status_icon.set_kind("alert", "warning")
        else:
            self.status_text.setText("NEXUS uses these when answering. They stay on this PC"
                                     + (" and are also shared with Gemini for online answers." if shared
                                        else " and are never sent to online AI."))
            self.status_icon.set_kind("info", "accent")
        self._clear(self.list_layout)
        query = self.search.text().strip() if hasattr(self, "search") else ""
        try:
            memories = self.store.search(query) if query else self.store.list()
        except Exception as error:  # noqa: BLE001
            self.list_layout.addWidget(EmptyState("alert", "Memories could not be loaded", str(error)))
            return
        if not memories:
            if query:
                self.list_layout.addWidget(EmptyState("search", "No matching memories", f"Nothing matches \"{query}\".", compact=True))
            else:
                self.list_layout.addWidget(EmptyState(
                    "memory", "Nothing remembered yet",
                    "Add a fact above, or tell NEXUS \"remember that my sister is Aline\".",
                ))
            return
        count = QLabel(f"{len(memories)} MEMOR{'IES' if len(memories) != 1 else 'Y'}")
        count.setObjectName("sectionLabel")
        count.setContentsMargins(10, 4, 0, 4)
        self.list_layout.addWidget(count)
        from ui.components import friendly_time

        for memory in reversed(memories):
            row, layout = _row(IconLabel("sparkle", 17, "accent"), memory.content,
                               "Saved " + (friendly_time(memory.created_at, with_time=False) or "earlier"))
            edit = IconButton("edit", "Edit memory", size=30, icon_size=16)
            edit.clicked.connect(lambda _=False, m=memory: self._edit(m))
            layout.addWidget(edit, 0, Qt.AlignVCenter)
            delete = IconButton("trash", "Forget this", size=30, icon_size=16)
            delete.clicked.connect(lambda _=False, m=memory: self._delete(m))
            layout.addWidget(delete, 0, Qt.AlignVCenter)
            self.list_layout.addWidget(row)

    def add_from_input(self):
        text = self.input.text().strip()
        if not text:
            self.input.setFocus()
            return
        for prefix in ("remember that ", "remember "):
            if text.lower().startswith(prefix):
                text = text[len(prefix):]
        try:
            self.store.add(text)
        except ValueError as error:
            self.toast.emit(str(error), "error")
            return
        self.input.clear()
        self.toast.emit("NEXUS will remember that.", "success")
        self.refresh()

    def _edit(self, memory):
        text, ok = QInputDialog.getText(self, "Edit memory", "Memory:", text=memory.content)
        if not ok or not text.strip():
            return
        try:
            self.store.update(memory.id, text.strip())
        except ValueError as error:
            self.toast.emit(str(error), "error")
        self.refresh()

    def _delete(self, memory):
        try:
            self.store.delete(memory.id)
            self.toast.emit("Forgotten.", "success")
        except ValueError as error:
            self.toast.emit(str(error), "error")
        self.refresh()

    def _clear_all(self):
        if QMessageBox.question(self, "Forget everything", "Delete every saved memory? This cannot be undone.",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            removed = self.store.clear()
            self.toast.emit(f"Deleted {removed} memor{'ies' if removed != 1 else 'y'}.", "success")
        except Exception as error:  # noqa: BLE001
            self.toast.emit(str(error), "error")
        self.refresh()


# ============================================================================= activity
ACTIVITY_ICONS = (
    (("error", "unavailable", "could not", "failed"), "alert", "danger"),
    (("reminder",), "bell", "accent"),
    (("voice", "microphone", "listening", "speech", "spoken"), "mic", "listening"),
    (("command", "executing", "windows"), "terminal", "muted"),
    (("settings", "appearance", "theme"), "settings", "muted"),
    (("summary", "summaris", "document", "file"), "file", "muted"),
    (("conversation", "chat"), "chat", "muted"),
)


def activity_icon(text: str) -> tuple[str, str]:
    lowered = str(text).lower()
    for words, icon, role in ACTIVITY_ICONS:
        if any(word in lowered for word in words):
            return icon, role
    return "activity", "accent"


class ActivityPage(_Page):
    clearRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("Activity", "What NEXUS has done during this session.", parent)
        self.events: list[tuple[str, str]] = []
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter activity")
        self.filter.setClearButtonEnabled(True)
        self.filter.setMaximumWidth(260)
        self.filter.textChanged.connect(lambda *_: self.set_events(self.events))
        self.header.actions.addWidget(self.filter)
        clear = QPushButton("Clear")
        clear.setObjectName("ghostButton")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self.clearRequested.emit)
        self.header.actions.addWidget(clear)
        self.card = Card()
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(0)
        self.card.body.addLayout(self.list_layout)
        self.layout_.addWidget(self.card)
        self.layout_.addStretch(1)
        self.set_events([])

    def set_events(self, events):
        self.events = list(events)
        if not self.isVisible() and self.list_layout.count():
            self._dirty = True
            return
        self._render()

    def showEvent(self, event):
        if getattr(self, "_dirty", False):
            self._dirty = False
            self._render()
        super().showEvent(event)

    def _render(self):
        self._clear(self.list_layout)
        query = self.filter.text().strip().lower()
        shown = [(stamp, text) for stamp, text in reversed(self.events) if not query or query in text.lower()]
        if not shown:
            self.list_layout.addWidget(EmptyState(
                "activity", "No activity yet" if not query else "Nothing matches",
                "Requests, voice, reminders and commands appear here as they happen." if not query else "",
            ))
            return
        for stamp, text in shown:
            icon, role = activity_icon(text)
            row, layout = _row(IconLabel(icon, 16, role), text)
            time_label = QLabel(stamp)
            time_label.setObjectName("rowMeta")
            layout.addWidget(time_label, 0, Qt.AlignTop)
            self.list_layout.addWidget(row)
