import ctypes
import queue
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QMenu,
    QProgressDialog,
    QSystemTrayIcon,
)

from core.background_voice import NexusBackgroundVoice
from core.dependency_manager import NexusDependencyManager
from ui.main_window import MainWindow


def resource_path(relative_path):
    """Return the correct path to a bundled resource."""
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / relative_path


def _activate_existing_nexus():
    """Bring an already-running NEXUS window to the foreground on Windows."""
    if sys.platform != "win32":
        return False

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, "NEXUS")
    if not hwnd:
        return False

    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    try:
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    try:
        user32.BringWindowToTop(hwnd)
    except Exception:
        pass
    return True


def _warm_up_ai(window):
    """Warm the local Ollama model without blocking the Qt interface."""
    try:
        ai_service = window.command_engine.ai
        ai_service.warm_up()
    except Exception:
        pass


def _single_instance():
    """Prevent multiple NEXUS processes from creating duplicate voice listeners."""
    if sys.platform != "win32":
        return None, True

    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "NEXUS_SINGLE_INSTANCE_2026")
    already_running = kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    return mutex, not already_running


def _prepare_dependencies(app, show_dialog=True):
    """Check/install Ollama and llama3.1:8b before NEXUS becomes operational."""
    messages = queue.Queue()
    result = {}

    def report(message):
        messages.put(str(message))

    def worker():
        manager = NexusDependencyManager(status_callback=report)
        success, detail = manager.ensure()
        result["success"] = success
        result["detail"] = detail

    dialog = None
    if show_dialog:
        dialog = QProgressDialog(
            "Checking NEXUS requirements...",
            None,
            0,
            0,
        )
        dialog.setWindowTitle("NEXUS Setup")
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setMinimumWidth(520)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setCancelButton(None)
        dialog.show()

    thread = threading.Thread(
        target=worker,
        name="NEXUS-Dependency-Setup",
        daemon=True,
    )
    thread.start()

    while thread.is_alive():
        try:
            while True:
                message = messages.get_nowait()
                if dialog is not None:
                    dialog.setLabelText(message)
        except queue.Empty:
            pass

        app.processEvents()
        time.sleep(0.05)

    thread.join(timeout=1.0)

    if dialog is not None:
        try:
            while True:
                dialog.setLabelText(messages.get_nowait())
        except queue.Empty:
            pass

        dialog.close()
    else:
        # Drain status messages so a long-running background setup does not
        # leave stale UI work queued for a later event loop iteration.
        try:
            while True:
                messages.get_nowait()
        except queue.Empty:
            pass

    return bool(result.get("success")), str(
        result.get("detail", "Dependency setup did not return a result.")
    )


def _start_hotkey_helper():
    """Start the separate resident Ctrl+Alt+N helper if it is available."""
    import subprocess

    if sys.platform != "win32":
        return

    if getattr(sys, "frozen", False):
        helper = Path(sys.executable).resolve().parent / "NEXUSHotkey.exe"
        if helper.exists():
            try:
                subprocess.Popen(
                    [str(helper)],
                    cwd=str(helper.parent),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                pass
        return

    script = Path(__file__).resolve().parent / "hotkey_helper.py"
    if script.exists():
        try:
            subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(script.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass

def main():
    # The resident hotkey helper launches NEXUS with --activate. If NEXUS is
    # already running, activate that instance instead of creating a second one.
    activate_requested = "--activate" in sys.argv

    mutex, is_first_instance = _single_instance()
    if not is_first_instance:
        if activate_requested and _activate_existing_nexus():
            print("[0] Existing NEXUS instance activated.")
        else:
            print("[0] NEXUS is already running.")
        return 0

    background_mode = "--background" in sys.argv
    setup_only = "--setup-dependencies" in sys.argv

    print("[1] Creating QApplication")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    print("[2] Setting application font")
    app.setFont(QFont("Segoe UI", 10))

    print("[3] Loading icon")
    icon_path = resource_path("assets/nexus.ico")
    nexus_icon = QIcon(str(icon_path))
    app.setWindowIcon(nexus_icon)

    print("[3a] Starting resident NEXUS hotkey helper")
    _start_hotkey_helper()

    # ---------------------------------------------------------
    # Automatic dependency preparation
    # ---------------------------------------------------------
    print("[4] Checking Ollama and llama3.1:8b")
    dependencies_ok, dependency_detail = _prepare_dependencies(
        app,
        show_dialog=not background_mode,
    )

    if setup_only:
        if dependencies_ok:
            print(f"[4a] {dependency_detail}")
            return 0

        print(f"[4a] Dependency setup failed: {dependency_detail}")
        return 1

    if not dependencies_ok:
        QMessageBox.warning(
            None,
            "NEXUS requirements",
            "NEXUS could not finish preparing Ollama and the local AI model.\n\n"
            f"{dependency_detail}\n\n"
            "NEXUS will still start so you can review the system check.",
        )

    print("[5] Creating MainWindow")
    window = MainWindow()

    print("[6] Setting MainWindow icon")
    window.setWindowIcon(nexus_icon)

    # ---------------------------------------------------------
    # Background voice assistant
    # ---------------------------------------------------------
    print("[8] Starting NEXUS background voice listener")
    background_voice = NexusBackgroundVoice(
        command_engine=window.command_engine,
        on_activate=window.activate_nexus,
        on_status=lambda message: print(f"[VOICE] {message}"),
    )
    window.set_background_voice(background_voice)
    background_voice.start()
    app.aboutToQuit.connect(background_voice.stop)

    # ---------------------------------------------------------
    # System tray
    # ---------------------------------------------------------
    tray = QSystemTrayIcon(nexus_icon, parent=app)
    tray.setToolTip("NEXUS — Personal Digital Command Center")

    tray_menu = QMenu()
    show_action = tray_menu.addAction("Open NEXUS")
    show_action.triggered.connect(window.activate_nexus)

    tray_menu.addSeparator()
    exit_action = tray_menu.addAction("Exit NEXUS")
    exit_action.triggered.connect(app.quit)

    tray.setContextMenu(tray_menu)
    tray.activated.connect(
        lambda reason: window.activate_nexus()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()
    app.aboutToQuit.connect(tray.hide)

    if background_mode and not activate_requested:
        print("[9] Background mode enabled — NEXUS UI is hidden.")
        window.hide()
    else:
        print("[9] Showing MainWindow")
        window.show()
        if activate_requested:
            QTimer.singleShot(80, window.activate_nexus)

    threading.Thread(
        target=_warm_up_ai,
        args=(window,),
        name="NEXUS-Ollama-Warmup",
        daemon=True,
    ).start()

    print("[10] NEXUS ready — Ctrl+Alt+N helper, local wake detector, and voice control are enabled.")
    print("[11] Starting Qt event loop")
    exit_code = app.exec()

    # Keep the mutex alive until the Qt process exits.
    _ = mutex
    print("[12] Qt event loop exited")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
