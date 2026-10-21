"""Shared test setup.

Every test runs against a throw-away data folder, a throw-away QSettings store,
no system keyring and no cloud credentials, so the suite can never touch real
user data or make a paid API call.

The environment must be prepared *before* any NEXUS module is imported, because
``config.settings`` reads it at import time - hence the module-level code.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_SESSION_DIR = Path(tempfile.mkdtemp(prefix="nexus-tests-"))
os.environ["NEXUS_DATA_DIR"] = str(_SESSION_DIR / "userdata")
os.environ["XDG_CONFIG_HOME"] = str(_SESSION_DIR / "xdg-config")
os.environ["XDG_DATA_HOME"] = str(_SESSION_DIR / "xdg-data")
os.environ["HOME"] = str(_SESSION_DIR / "home")
os.environ["NEXUS_DISABLE_KEYRING"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
for _name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "NEXUS_GEMINI_API_KEY", "OPENAI_API_KEY", "LOCALAPPDATA"):
    os.environ.pop(_name, None)
Path(os.environ["HOME"]).mkdir(parents=True, exist_ok=True)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """A private data folder for one test (credential fallback files, etc.)."""
    folder = tmp_path / "nexus-data"
    monkeypatch.setenv("NEXUS_DATA_DIR", str(folder))
    return folder


@pytest.fixture()
def db(tmp_path):
    from database.database import Database

    return Database(tmp_path / "db")


@pytest.fixture()
def settings():
    """Fresh settings (QSettings lives in the temp XDG folder) reset to defaults."""
    from config.settings import NEXUSSettings

    s = NEXUSSettings()
    s.reset()
    yield s
    s.reset()


@pytest.fixture()
def engine(db, settings):
    from core.assistant import AssistantEngine

    return AssistantEngine(database=db, settings=settings)
