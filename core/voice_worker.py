from PySide6.QtCore import QObject, Signal, Slot

from core.voice import VoiceService


class VoiceListenWorker(QObject):
    finished = Signal(str, str)
    error = Signal(str)
    started = Signal()

    def __init__(self, language="auto"):
        super().__init__()
        self.language = str(language or "auto")

    @Slot()
    def run(self):
        self.started.emit()
        try:
            voice_service = VoiceService()
            text, language = voice_service.listen(self.language)
            self.finished.emit(text, language)
        except Exception as error:
            self.error.emit(str(error))


class VoiceSpeakWorker(QObject):
    finished = Signal()
    error = Signal(str)
    started = Signal()

    def __init__(self, text, language="auto"):
        super().__init__()
        self.text = str(text)
        self.language = str(language or "auto")

    @Slot()
    def run(self):
        self.started.emit()
        try:
            voice_service = VoiceService()
            voice_service.speak(self.text, self.language)
            self.finished.emit()
        except Exception as error:
            self.error.emit(str(error))
