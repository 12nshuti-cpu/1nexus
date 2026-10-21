"""Credential storage for NEXUS.

Order of preference when *saving*:

1. The operating system credential store through ``keyring``
   (Windows Credential Manager on Windows) - encrypted for the signed-in user.
2. Fallback only when no usable credential store exists: a plain-text file in
   the per-user NEXUS data folder (``%LOCALAPPDATA%\\NEXUS``), never inside the
   program folder or a source checkout.

When *reading*, environment variables are handled by callers (they win), then
the credential store, then the legacy files used by earlier NEXUS versions.
A key found in the legacy per-user file is migrated into the credential store
(verified by reading it back) and the plain-text file is then removed.

Secrets are never logged by this module.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

SERVICE_NAME = "NEXUS"


def _data_dir() -> Path:
    override = os.environ.get("NEXUS_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "NEXUS"
    if os.name == "nt":
        return Path.home() / "AppData" / "Local" / "NEXUS"
    return Path.home() / ".local" / "share" / "NEXUS"


def fallback_file(name: str) -> Path:
    return _data_dir() / f"{name}.txt"


def _usable_keyring():
    """Return the ``keyring`` module if a real encrypted backend is available."""
    if os.environ.get("NEXUS_DISABLE_KEYRING") == "1":
        return None
    try:
        import keyring

        backend = keyring.get_keyring()
        label = f"{type(backend).__module__}.{type(backend).__name__}".lower()
        if "fail" in label or "null" in label or "chainer" in label and not getattr(backend, "backends", None):
            return None
        return keyring
    except Exception:  # noqa: BLE001 - keyring missing or misconfigured
        return None


def backend_description() -> str:
    store = _usable_keyring()
    if store is None:
        return f"a protected file in {_data_dir()} (no system credential store available)"
    return "the system credential store (Windows Credential Manager on Windows)"


def _read_file(path: Path) -> str:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return ""


def get_secret(name: str, legacy_paths: Iterable[Path] = ()) -> str:
    """Return the stored secret ``name`` or an empty string."""
    store = _usable_keyring()
    standard = fallback_file(name)

    if store is not None:
        try:
            value = store.get_password(SERVICE_NAME, name) or ""
        except Exception:  # noqa: BLE001
            value = ""
        if value:
            return value
        migrated = _read_file(standard)
        if migrated:
            try:
                store.set_password(SERVICE_NAME, name, migrated)
                if store.get_password(SERVICE_NAME, name) == migrated:
                    try:
                        standard.unlink()  # plain-text copy no longer needed
                    except OSError:
                        pass
            except Exception:  # noqa: BLE001 - keep the file if migration failed
                pass
            return migrated
    else:
        value = _read_file(standard)
        if value:
            return value

    for path in legacy_paths:
        value = _read_file(Path(path))
        if value:
            return value
    return ""


def set_secret(name: str, value: str) -> str:
    """Save a secret. Returns a short, human-readable description of where."""
    secret = str(value or "").strip()
    if not secret:
        raise ValueError("The secret cannot be empty.")

    store = _usable_keyring()
    if store is not None:
        try:
            store.set_password(SERVICE_NAME, name, secret)
            if store.get_password(SERVICE_NAME, name) == secret:
                try:
                    fallback_file(name).unlink()
                except OSError:
                    pass
                return "the system credential store"
        except Exception:  # noqa: BLE001 - fall through to the file fallback
            pass

    path = fallback_file(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(secret + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return str(path)


def delete_secret(name: str) -> None:
    store = _usable_keyring()
    if store is not None:
        try:
            store.delete_password(SERVICE_NAME, name)
        except Exception:  # noqa: BLE001 - not stored is fine
            pass
    try:
        fallback_file(name).unlink()
    except OSError:
        pass


def has_secret(name: str, legacy_paths: Iterable[Path] = ()) -> bool:
    return bool(get_secret(name, legacy_paths))
