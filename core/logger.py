"""Application logging for NEXUS.

* Logs go to a rotating file in the per-user log folder
  (``%LOCALAPPDATA%\\NEXUS\\logs\\nexus.log`` on Windows) so a windowed/packaged
  build, which has no console, is still diagnosable.
* Anything that looks like an API key or bearer token is masked before it is
  written, so a log file can be attached to a bug report safely.
* Uncaught exceptions (main thread and worker threads) are logged instead of
  silently disappearing.
"""
from __future__ import annotations

import logging
import re
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_NAME = "nexus"
LOG_FILE_NAME = "nexus.log"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

# Order matters: more specific shapes first.
_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),                       # Google API keys
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),                         # OpenAI-style keys
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}"),            # bearer tokens
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*[=:]\s*)[^\s,;&\"']{6,}"),
    re.compile(r"(?i)([?&]key=)[^&\s]{6,}"),                       # ?key=... in URLs
)


def redact(text: str) -> str:
    """Mask anything that looks like a credential."""
    value = str(text)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            value = pattern.sub(lambda m: m.group(1) + "[REDACTED]", value)
        else:
            value = pattern.sub("[REDACTED]", value)
    return value


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:  # noqa: BLE001 - logging must never raise
            pass
        return True


_configured = False


def default_log_dir() -> Path:
    from config.settings import USER_LOG_DIR

    return Path(USER_LOG_DIR)


def log_file_path(log_dir: Path | None = None) -> Path:
    return Path(log_dir or default_log_dir()) / LOG_FILE_NAME


def configure_logging(
    log_dir: Path | None = None,
    level: int | str = logging.INFO,
    *,
    console: bool | None = None,
    force: bool = False,
) -> Path:
    """Configure the ``nexus`` logger once and return the log-file path."""
    global _configured
    logger = logging.getLogger(LOG_NAME)
    path = log_file_path(log_dir)
    if _configured and not force:
        return path

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # noqa: BLE001
            pass

    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter(_FORMAT)
    redactor = _RedactingFilter()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redactor)
        logger.addHandler(file_handler)
    except OSError:
        pass  # read-only profile etc.: fall back to console only

    if console is None:
        console = sys.stderr is not None and not getattr(sys, "frozen", False)
    if console and sys.stderr is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        stream.addFilter(redactor)
        logger.addHandler(stream)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    _configured = True
    return path


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOG_NAME}.{name}" if name else LOG_NAME)


def install_exception_hooks() -> None:
    """Log uncaught exceptions from the main thread and from worker threads."""
    log = get_logger("crash")

    def _main_hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def _thread_hook(args):
        if args.exc_type is SystemExit:
            return
        log.error(
            "Uncaught exception in thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _main_hook
    threading.excepthook = _thread_hook
