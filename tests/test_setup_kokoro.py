"""Tests for scripts/setup_kokoro.py (interpreter selection and paths; no network)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "setup_kokoro.py"


@pytest.fixture(scope="module")
def setup_kokoro():
    spec = importlib.util.spec_from_file_location("setup_kokoro", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["setup_kokoro"] = module
    spec.loader.exec_module(module)
    return module


def fake_runner(table):
    """Return a runner that answers for interpreter commands listed in ``table``."""

    def run(command):
        key = tuple(command[:-2])  # strip the "-c <code>" suffix
        if key not in table:
            raise FileNotFoundError(key)
        path, version = table[key]
        return subprocess.CompletedProcess(command, 0, stdout=f"{path}\n{version[0]} {version[1]}\n", stderr="")

    return run


@pytest.mark.parametrize("version,ok", [((3, 9), False), ((3, 10), True), ((3, 12), True), ((3, 13), False), ((3, 14), False)])
def test_version_window_matches_kokoro_requirement(setup_kokoro, version, ok):
    assert setup_kokoro.version_ok(version) is ok


def test_explicit_python_outside_window_is_rejected(setup_kokoro):
    runner = fake_runner({("/opt/py313",): ("/opt/py313", (3, 13))})
    assert setup_kokoro.find_interpreter("/opt/py313", runner) is None


def test_explicit_python_inside_window_is_used(setup_kokoro):
    runner = fake_runner({("/opt/py312",): ("/opt/py312", (3, 12))})
    assert setup_kokoro.find_interpreter("/opt/py312", runner) == Path("/opt/py312")


def test_unusable_interpreter_returns_none(setup_kokoro):
    assert setup_kokoro.find_interpreter("/does/not/exist", fake_runner({})) is None


def test_probe_handles_garbage_output(setup_kokoro):
    def runner(command):
        return subprocess.CompletedProcess(command, 0, stdout="hello\nnot numbers\n", stderr="")

    assert setup_kokoro.probe_interpreter(["python"], runner) is None


def test_default_data_dir_honours_override(setup_kokoro, monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
    assert setup_kokoro.default_data_dir() == tmp_path / "kokoro"


def test_default_data_dir_matches_the_app(setup_kokoro, monkeypatch, tmp_path):
    """The installer must put the venv exactly where core.speech looks for it."""
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
    from core import speech

    monkeypatch.setattr("config.settings.USER_DATA_DIR", tmp_path)
    assert speech.kokoro_env_dir() == setup_kokoro.default_data_dir()


def test_check_reports_not_installed(setup_kokoro, tmp_path, capsys):
    assert setup_kokoro.main(["--check", "--dir", str(tmp_path / "none")]) == 1
    assert "not installed" in capsys.readouterr().out


def test_worker_script_exists_where_the_installer_expects_it(setup_kokoro):
    assert setup_kokoro.WORKER.is_file()
