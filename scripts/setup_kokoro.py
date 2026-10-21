"""Install the optional Kokoro text-to-speech runtime for NEXUS.

Why this exists
---------------
Kokoro (PyPI ``kokoro``) requires Python >= 3.10 and < 3.13, while NEXUS itself
may run on a newer interpreter or as a packaged .exe. So Kokoro lives in its own
virtual environment, and NEXUS talks to it through ``core/kokoro_tts_worker.py``.

This script (standard library only):

1. finds a compatible Python (3.10, 3.11 or 3.12),
2. creates ``<NEXUS data folder>/kokoro/venv``,
3. installs ``kokoro``, ``soundfile`` and ``numpy`` into it,
4. starts the real worker and checks that it reports ready,
5. optionally synthesises one short phrase, which downloads the voice model
   (roughly 330 MB, from Hugging Face) the first time.

Nothing is installed anywhere else, and nothing is changed if a step fails.

Usage::

    python scripts/setup_kokoro.py [--python PATH] [--dir DIR] [--no-warmup]
                                   [--torch-index-url URL] [--check]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

MIN_VERSION = (3, 10)
MAX_VERSION_EXCLUSIVE = (3, 13)
PACKAGES = ["kokoro>=0.9.4", "soundfile", "numpy"]
WORKER = Path(__file__).resolve().parents[1] / "core" / "kokoro_tts_worker.py"

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


def say(message: str) -> None:
    print(message, flush=True)


def default_data_dir() -> Path:
    """Mirror config.settings._user_data_dir() without importing the app."""
    override = os.environ.get("NEXUS_DATA_DIR")
    if override:
        return Path(override) / "kokoro"
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "NEXUS" / "kokoro"
    xdg = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return root / "NEXUS" / "kokoro"


def version_ok(version: tuple[int, int]) -> bool:
    return MIN_VERSION <= tuple(version[:2]) < MAX_VERSION_EXCLUSIVE


def _run(command: Sequence[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(list(command), capture_output=True, text=True, timeout=60, check=False)


def probe_interpreter(command: Sequence[str], runner: Runner = _run) -> Optional[tuple[Path, tuple[int, int]]]:
    """Ask an interpreter for its real path and version; None if unusable."""
    try:
        result = runner([*command, "-c", "import sys;print(sys.executable);print(sys.version_info[0], sys.version_info[1])"])
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    try:
        major, minor = (int(part) for part in lines[-1].split()[:2])
    except ValueError:
        return None
    path = Path(lines[-2])
    return path, (major, minor)


def candidate_commands(explicit: Optional[str]) -> Iterable[list[str]]:
    if explicit:
        yield [explicit]
        return
    if os.name == "nt":
        for minor in (12, 11, 10):  # the Windows "py" launcher
            yield ["py", f"-3.{minor}"]
    for minor in (12, 11, 10):
        name = shutil.which(f"python3.{minor}")
        if name:
            yield [name]
    yield [sys.executable]
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            yield [found]


def find_interpreter(explicit: Optional[str] = None, runner: Runner = _run) -> Optional[Path]:
    seen: set[str] = set()
    for command in candidate_commands(explicit):
        probed = probe_interpreter(command, runner)
        if probed is None:
            continue
        path, version = probed
        if str(path) in seen:
            continue
        seen.add(str(path))
        if version_ok(version):
            return path
    return None


def venv_python(venv: Path) -> Optional[Path]:
    for rel in (("Scripts", "python.exe"), ("bin", "python")):
        candidate = venv.joinpath(*rel)
        if candidate.is_file():
            return candidate
    return None


def check_worker(python: Path, timeout: float = 300.0) -> tuple[bool, str]:
    """Start the real worker and wait for its ready message."""
    if not WORKER.is_file():
        return False, f"Worker script not found: {WORKER}"
    process = subprocess.Popen(
        [str(python), str(WORKER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
    )
    try:
        line = process.stdout.readline() if process.stdout else ""
        if not line:
            err = process.stderr.read() if process.stderr else ""
            return False, f"Worker exited without a ready message. {err.strip()[-400:]}"
        status = json.loads(line)
        if status.get("ready"):
            return True, "Kokoro worker is ready."
        return False, str(status.get("error") or "Kokoro worker reported a failure.")
    except (OSError, ValueError) as error:
        return False, f"Worker check failed: {error}"
    finally:
        try:
            if process.stdin:
                process.stdin.close()
            process.terminate()
            process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            process.kill()


def warm_up(python: Path, timeout: float = 900.0) -> tuple[bool, str]:
    """Synthesise one phrase; the first run downloads the voice model."""
    process = subprocess.Popen(
        [str(python), str(WORKER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
    )
    try:
        ready = json.loads(process.stdout.readline() or "{}")
        if not ready.get("ready"):
            return False, str(ready.get("error") or "Kokoro worker did not start.")
        process.stdin.write(json.dumps({"text": "NEXUS voice test.", "lang": "a", "voice": "af_heart", "speed": 1.0}) + "\n")
        process.stdin.flush()
        reply = json.loads(process.stdout.readline() or "{}")
        if reply.get("ok") and reply.get("path") and Path(reply["path"]).is_file():
            try:
                Path(reply["path"]).unlink()
            except OSError:
                pass
            return True, "Kokoro synthesised a test phrase."
        return False, str(reply.get("error") or "Kokoro produced no audio.")
    except (OSError, ValueError) as error:
        return False, f"Warm-up failed: {error}"
    finally:
        try:
            if process.stdin:
                process.stdin.close()
            process.terminate()
            process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            process.kill()


def install(base: Path, python: Path, torch_index_url: Optional[str], do_warmup: bool) -> int:
    venv = base / "venv"
    existing = venv_python(venv)
    if existing is None:
        say(f"Creating Kokoro environment in {venv} using {python} ...")
        base.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([str(python), "-m", "venv", str(venv)], capture_output=True, text=True)
        if result.returncode != 0:
            say(f"Could not create the environment:\n{result.stderr.strip()[-600:]}")
            return 3
        existing = venv_python(venv)
    if existing is None:
        say("The environment was created but has no Python executable.")
        return 3

    say("Installing Kokoro (this downloads PyTorch; it can take several minutes) ...")
    command = [str(existing), "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip"]
    subprocess.run(command, capture_output=True, text=True)
    pip = [str(existing), "-m", "pip", "install", "--disable-pip-version-check"]
    if torch_index_url:
        say(f"Installing PyTorch from {torch_index_url} ...")
        result = subprocess.run([*pip, "torch", "--index-url", torch_index_url], text=True)
        if result.returncode != 0:
            say("PyTorch installation failed.")
            return 4
    result = subprocess.run([*pip, *PACKAGES], text=True)
    if result.returncode != 0:
        say("Kokoro installation failed. Your environment was left in place; run this script again to retry.")
        return 4

    ok, detail = check_worker(existing)
    say(detail)
    if not ok:
        return 5
    if do_warmup:
        say("Downloading the voice model and testing speech (about 330 MB the first time) ...")
        ok, detail = warm_up(existing)
        say(detail)
        if not ok:
            say("The environment is installed, but the voice test failed. Check your internet connection and run again.")
            return 6
    say(f"Done. Kokoro is installed at {venv}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Install the optional Kokoro voice runtime for NEXUS.")
    parser.add_argument("--python", help="Path to a Python 3.10-3.12 interpreter to use.")
    parser.add_argument("--dir", help="Install folder (default: the NEXUS data folder /kokoro).")
    parser.add_argument("--no-warmup", action="store_true", help="Skip the voice-model download and test phrase.")
    parser.add_argument("--torch-index-url", help="Alternative PyTorch wheel index (e.g. a CPU-only index).")
    parser.add_argument("--check", action="store_true", help="Only report whether Kokoro is already installed and working.")
    args = parser.parse_args(argv)

    base = Path(args.dir) if args.dir else default_data_dir()
    if args.check:
        existing = venv_python(base / "venv")
        if existing is None:
            say("Kokoro is not installed.")
            return 1
        ok, detail = check_worker(existing)
        say(detail)
        return 0 if ok else 5

    python = find_interpreter(args.python)
    if python is None:
        say(
            "No compatible Python found. Kokoro needs Python 3.10, 3.11 or 3.12 (not 3.13+).\n"
            "Install one from https://www.python.org/downloads/ (tick 'py launcher'), then run this again.\n"
            "NEXUS keeps working with the Windows voice in the meantime."
        )
        return 2
    return install(base, python, args.torch_index_url, do_warmup=not args.no_warmup)


if __name__ == "__main__":
    raise SystemExit(main())
