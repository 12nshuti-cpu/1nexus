from PySide6.QtCore import QObject, Signal, Slot


class AIWorker(QObject):
    """Run AI generation off the UI thread and forward text/speech chunks."""

    chunk = Signal(int, str)
    speech_chunk = Signal(int, str, str)
    finished = Signal(int, str, str)
    error = Signal(int, str, str)

    def __init__(
        self, ai_service, conversation_id, message, conversation,
        speech_enabled=False, speech_language="auto",
    ):
        super().__init__()
        self.ai_service = ai_service
        self.conversation_id = conversation_id
        self.message = message
        self.conversation = conversation
        self.speech_enabled = bool(speech_enabled)
        self.speech_language = str(speech_language or "auto")

    @Slot()
    def run(self):
        try:
            ask_stream = getattr(self.ai_service, "ask_stream", None)
            if callable(ask_stream):
                kwargs = {
                    "on_chunk": lambda text: self.chunk.emit(self.conversation_id, str(text)),
                }
                # Only the local Ollama streaming branch invokes this callback; online
                # Gemini responses retain their existing route and voice behavior.
                if self.speech_enabled:
                    kwargs["on_speech_chunk"] = lambda text: self.speech_chunk.emit(
                        self.conversation_id, str(text), self.speech_language
                    )
                    kwargs["spoken"] = True  # ask for a conversational reply, not a written one
                response = ask_stream(self.message, self.conversation, **kwargs)
            else:
                response = self.ai_service.ask(self.message, self.conversation)
                self.chunk.emit(self.conversation_id, response)
            self.finished.emit(self.conversation_id, self.message, response)
        except Exception as error:
            self.error.emit(self.conversation_id, self.message, str(error))
