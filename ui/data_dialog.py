"""Reminders, memories and personal-data management window.

Everything here is a thin view over the same stores the assistant uses, so
what the user sees is exactly what NEXUS has saved - and they can edit or
erase all of it.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import NEXUSSettings
from core import data_export
from core.timeparse import describe_due, parse_time


class DataDialog(QDialog):
    """Tabs: Reminders - Memories - Privacy & data."""

    def __init__(self, assistant, settings: NEXUSSettings | None = None, parent=None):
        super().__init__(parent)
        self.assistant = assistant
        self.settings = settings or NEXUSSettings()
        self.setWindowTitle("NEXUS - Reminders, memory & data")
        self.setMinimumSize(640, 480)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._build_reminders(), "Reminders")
        self.tabs.addTab(self._build_memories(), "Memories")
        self.tabs.addTab(self._build_privacy(), "Privacy && data")

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)

        self.refresh()

    # ------------------------------------------------------------------ builders
    @staticmethod
    def _buttons(*pairs):
        row = QHBoxLayout()
        for label, callback in pairs:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch()
        return row

    def _build_reminders(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel(
            "Reminders notify you while NEXUS is running (it can stay in the system tray). "
            "If one comes due while NEXUS is closed, you are told at the next launch."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.reminder_list = QListWidget()
        layout.addWidget(self.reminder_list)
        self.show_done = QCheckBox("Show completed reminders")
        self.show_done.toggled.connect(self.refresh)
        layout.addWidget(self.show_done)
        layout.addLayout(self._buttons(
            ("Add...", self.add_reminder),
            ("Reschedule...", self.reschedule_reminder),
            ("Mark done", self.complete_reminder),
            ("Delete", self.delete_reminder),
        ))
        return page

    def _build_memories(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel(
            "Only things you explicitly asked NEXUS to remember are stored here "
            "(say \"remember that ...\"). Nothing is collected automatically."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.memory_list = QListWidget()
        layout.addWidget(self.memory_list)
        layout.addLayout(self._buttons(
            ("Add...", self.add_memory),
            ("Edit...", self.edit_memory),
            ("Delete", self.delete_memory),
            ("Forget everything", self.clear_memories),
        ))
        return page

    def _build_privacy(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.personalization = QCheckBox("Personalization: let NEXUS save and use memories")
        self.personalization.setChecked(self.settings.personalization_enabled)
        self.personalization.toggled.connect(self._set_personalization)
        layout.addWidget(self.personalization)

        self.share_online = QCheckBox("Include my memories when a request is sent to the online AI (off by default)")
        self.share_online.setChecked(self.settings.share_memory_with_online)
        self.share_online.toggled.connect(self._set_share_online)
        layout.addWidget(self.share_online)

        info = QLabel(
            "Your conversations, reminders and memories are stored only on this PC. "
            "Text you send while the online AI is selected is sent to that provider to be answered."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.location_label = QLabel(f"Data file: {self.assistant.database.db_path}")
        self.location_label.setWordWrap(True)
        self.location_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.location_label)

        layout.addLayout(self._buttons(
            ("Export everything (JSON)...", self.export_json),
            ("Back up database...", self.backup_db),
        ))
        layout.addLayout(self._buttons(("Delete all conversations...", self.delete_conversations)))
        layout.addStretch()
        return page

    # ----------------------------------------------------------------- refreshing
    def refresh(self, *_):
        self.reminder_list.clear()
        now = datetime.now()
        for reminder in self.assistant.reminders.list(include_done=self.show_done.isChecked()):
            marks = {"pending": "", "fired": "[notified] ", "done": "[done] "}
            item = QListWidgetItem(f"#{reminder.id}  {marks.get(reminder.status, '')}{reminder.message} - {describe_due(reminder.due_at, now)}")
            item.setData(Qt.UserRole, reminder.id)
            self.reminder_list.addItem(item)
        self.memory_list.clear()
        for memory in self.assistant.memory.list():
            item = QListWidgetItem(f"#{memory.id}  {memory.content}")
            item.setData(Qt.UserRole, memory.id)
            self.memory_list.addItem(item)

    @staticmethod
    def _selected_id(widget: QListWidget):
        item = widget.currentItem()
        return None if item is None else int(item.data(Qt.UserRole))

    def _error(self, error: Exception):
        QMessageBox.warning(self, "NEXUS", str(error))

    # ------------------------------------------------------------------ reminders
    def add_reminder(self):
        text, ok = QInputDialog.getText(
            self, "Add reminder", "What and when? (e.g. call Sam in 10 minutes, or submit form tomorrow at 9am)"
        )
        if not ok or not text.strip():
            return
        from core.timeparse import parse_reminder

        parsed = parse_reminder("remind me to " + text.strip())
        if parsed is None:
            QMessageBox.information(self, "NEXUS", "I couldn't work out when. Try \"... in 10 minutes\" or \"... tomorrow at 9am\".")
            return
        try:
            self.assistant.reminders.create(parsed.message, parsed.due)
        except ValueError as error:
            self._error(error)
        self.refresh()

    def reschedule_reminder(self):
        reminder_id = self._selected_id(self.reminder_list)
        if reminder_id is None:
            return
        text, ok = QInputDialog.getText(self, "Reschedule", "New time (e.g. in 1 hour, tomorrow at 8am):")
        if not ok:
            return
        parsed = parse_time(text)
        if parsed is None:
            QMessageBox.information(self, "NEXUS", "I couldn't understand that time.")
            return
        try:
            self.assistant.reminders.update(reminder_id, None, parsed.due)
        except ValueError as error:
            self._error(error)
        self.refresh()

    def complete_reminder(self):
        reminder_id = self._selected_id(self.reminder_list)
        if reminder_id is not None:
            try:
                self.assistant.reminders.complete(reminder_id)
            except ValueError as error:
                self._error(error)
            self.refresh()

    def delete_reminder(self):
        reminder_id = self._selected_id(self.reminder_list)
        if reminder_id is not None:
            try:
                self.assistant.reminders.delete(reminder_id)
            except ValueError as error:
                self._error(error)
            self.refresh()

    # ------------------------------------------------------------------- memories
    def add_memory(self):
        if not self.settings.personalization_enabled:
            QMessageBox.information(self, "NEXUS", "Personalization is turned off (Privacy && data tab).")
            return
        text, ok = QInputDialog.getText(self, "Add memory", "What should NEXUS remember?")
        if ok and text.strip():
            try:
                self.assistant.memory.add(text)
            except ValueError as error:
                self._error(error)
            self.refresh()

    def edit_memory(self):
        memory_id = self._selected_id(self.memory_list)
        if memory_id is None:
            return
        current = self.assistant.memory.get(memory_id).content
        text, ok = QInputDialog.getText(self, "Edit memory", "Memory:", text=current)
        if ok and text.strip():
            try:
                self.assistant.memory.update(memory_id, text)
            except ValueError as error:
                self._error(error)
            self.refresh()

    def delete_memory(self):
        memory_id = self._selected_id(self.memory_list)
        if memory_id is not None:
            try:
                self.assistant.memory.delete(memory_id)
            except ValueError as error:
                self._error(error)
            self.refresh()

    def clear_memories(self):
        if QMessageBox.question(
            self, "Forget everything", "Permanently delete every saved memory?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) == QMessageBox.Yes:
            self.assistant.memory.clear()
            self.refresh()

    # -------------------------------------------------------------- privacy / data
    def _set_personalization(self, value: bool):
        self.settings.personalization_enabled = bool(value)

    def _set_share_online(self, value: bool):
        self.settings.share_memory_with_online = bool(value)

    def export_json(self):
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export NEXUS data", str(Path.home() / f"nexus-export-{stamp}.json"), "JSON (*.json)"
        )
        if path:
            try:
                data_export.export_json(path, self.assistant.database)
                QMessageBox.information(self, "NEXUS", f"Exported to:\n{path}")
            except OSError as error:
                self._error(error)

    def backup_db(self):
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        path, _ = QFileDialog.getSaveFileName(
            self, "Back up NEXUS database", str(Path.home() / f"nexus-backup-{stamp}.db"), "SQLite database (*.db)"
        )
        if path:
            try:
                data_export.backup_database(path, self.assistant.database)
                QMessageBox.information(self, "NEXUS", f"Backup saved to:\n{path}")
            except (OSError, Exception) as error:  # noqa: BLE001
                self._error(error)

    def delete_conversations(self):
        if QMessageBox.question(
            self, "Delete conversations",
            "Permanently delete ALL conversation history? Reminders and memories are kept.\n\n"
            "Restart NEXUS afterwards so the conversation list refreshes.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) == QMessageBox.Yes:
            count = data_export.delete_conversations(self.assistant.database)
            QMessageBox.information(self, "NEXUS", f"Deleted {count} conversation(s).")
