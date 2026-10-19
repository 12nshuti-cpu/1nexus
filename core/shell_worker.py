from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from core.shell_executor import ShellExecutor


class ShellCommandWorker(QObject):
    started = Signal()
    finished = Signal(str, bool)
    error = Signal(str)

    def __init__(self, command: str):
        super().__init__()
        self.command = str(command)

    @Slot()
    def run(self):
        self.started.emit()
        try:
            executor = ShellExecutor()
            result = executor.execute(self.command)
            self.finished.emit(executor.format_response(result), result.success)
        except Exception as error:
            self.error.emit(str(error))
