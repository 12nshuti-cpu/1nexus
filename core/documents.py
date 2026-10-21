"""Reading a document the user chose, so NEXUS can summarise it.

Rules
-----
* Only plain-text style files are supported (see :data:`ALLOWED_SUFFIXES`). PDF and Word
  files are not supported yet and the user is told so, rather than getting garbled text.
* The file is read, never written, moved or executed, and only because the *user* asked
  for it by name or through the file picker. This is deliberately not an AI-callable tool:
  text inside a document must not be able to make NEXUS read other files.
* Size is capped; very long files are truncated and the user is told.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ALLOWED_SUFFIXES = frozenset({
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml",
    ".ini", ".cfg", ".toml", ".html", ".htm", ".py", ".js", ".ts", ".css", ".sql", ".bat", ".ps1", ".sh",
})
UNSUPPORTED_HINTS = {
    ".pdf": "PDF files are not supported yet. Copy the text into a .txt file, or paste it into the chat.",
    ".docx": "Word files are not supported yet. Save the document as .txt, or paste the text into the chat.",
    ".doc": "Word files are not supported yet. Save the document as .txt, or paste the text into the chat.",
}
MAX_FILE_BYTES = 2_000_000
MAX_CHARS = 20_000

_REQUEST = re.compile(
    r"^(?:please\s+)?(?:summari[sz]e|summary\s+of)\s+(?:(?:this|the|a|my)\s+)?(?:(?:file|document|doc|text)\s+)?(?P<rest>.*)$",
    re.IGNORECASE,
)
_PICKER_WORDS = {"", "file", "document", "doc", "text", "a file", "a document", "this file", "this document"}


class DocumentError(ValueError):
    """The file cannot be read; the message is written for the user."""


@dataclass(frozen=True)
class Document:
    name: str
    path: Path
    text: str
    truncated: bool
    total_chars: int


def parse_summarize_request(text: str) -> Optional[str]:
    """Is this a request to summarise a *file*?

    Returns ``None`` when it is not (so ordinary questions such as "summarize the plot of
    Hamlet" still go to the AI), ``""`` when the user wants a file picker, or the path text.
    """
    match = _REQUEST.match(str(text or "").strip())
    if not match:
        return None
    rest = match.group("rest").strip().strip("\"'").strip()
    if rest.lower() in _PICKER_WORDS and re.search(r"\b(?:file|document|doc)\b", text, re.IGNORECASE):
        return ""
    suffix = Path(rest).suffix.lower()
    looks_like_path = bool(re.search(r"[\\/]", rest)) or bool(re.match(r"^[A-Za-z]:", rest))
    known_extension = suffix in ALLOWED_SUFFIXES or suffix in UNSUPPORTED_HINTS
    if rest and (looks_like_path or known_extension) and "\n" not in rest:
        return rest
    return None


def read_document(path: str | Path, *, max_chars: int = MAX_CHARS) -> Document:
    """Read a supported text file. Raises :class:`DocumentError` with a helpful message."""
    raw = str(path).strip().strip("\"'")
    if not raw:
        raise DocumentError("No file was chosen.")
    try:
        file = Path(raw).expanduser()
        if not file.is_file():
            raise DocumentError(f"I could not find a file at {raw}.")
        suffix = file.suffix.lower()
        if suffix in UNSUPPORTED_HINTS:
            raise DocumentError(UNSUPPORTED_HINTS[suffix])
        if suffix not in ALLOWED_SUFFIXES:
            raise DocumentError(
                f"{file.name}: I can only summarise text-based files ({', '.join(sorted(ALLOWED_SUFFIXES)[:8])}, ...)."
            )
        size = file.stat().st_size
        if size == 0:
            raise DocumentError(f"{file.name} is empty.")
        if size > MAX_FILE_BYTES:
            raise DocumentError(f"{file.name} is {size / 1_000_000:.1f} MB; the limit is {MAX_FILE_BYTES // 1_000_000} MB.")
        data = file.read_bytes()
    except DocumentError:
        raise
    except OSError as error:
        raise DocumentError(f"I could not read {raw}: {error.strerror or error}") from error

    if b"\x00" in data[:4096]:
        raise DocumentError(f"{file.name} looks like a binary file, not text.")
    text = data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").strip()
    if not text:
        raise DocumentError(f"{file.name} contains no readable text.")
    total = len(text)
    truncated = total > max_chars
    return Document(file.name, file.resolve(), text[:max_chars], truncated, total)
