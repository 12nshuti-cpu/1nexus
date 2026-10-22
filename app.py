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

from config.settings import APP_NAME, APP_VERSION, NEXUSSettings
from core.background_voice import NexusBackgroundVoice
from core.dependency_manager import NexusDependencyManager
from core.logger import configure_logging, get_logger, install_exception_hooks
from ui.main_window import MainWindow
from ui.theme import theme as nexus_theme


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

def _show_first_run_wizard(settings, log):
    """Run the first-run wizard once. Returns after the user finishes or skips."""
    from ui.first_run_wizard import FirstRunWizard

    wizard = FirstRunWizard(settings)
    wizard.exec()
    warnings = getattr(wizard, "last_warnings", [])
    for line in warnings:
        log.warning("first-run: %s", line)
    if warnings:
        QMessageBox.information(None, "NEXUS setup", "\n\n".join(warnings))


def _destroy_ui(app, *objects):
    """Delete Qt widgets while the QApplication still exists.

    If Python releases the QApplication before the widgets that belong to it (which depends on
    local-variable order and garbage-collection timing), Qt can crash during process exit.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    for obj in objects:
        if obj is None:
            continue
        try:
            obj.hide()
        except Exception:  # noqa: BLE001
            pass
        try:
            obj.deleteLater()
        except Exception:  # noqa: BLE001
            pass
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _selftest(log):
    """Build the real UI without showing it, check bundled resources, then exit.

    Used by scripts/build.ps1 to smoke-test the frozen app and by the test suite.
    It touches no network, starts no background services and ignores the
    single-instance lock, so it is safe to run while NEXUS is open.
    Returns 0 on success, 1 on failure.
    """
    problems = []
    for relative in ("assets/nexus.ico", "models/Modelfile", "core/kokoro_tts_worker.py"):
        if not resource_path(relative).is_file():
            problems.append(f"missing bundled resource: {relative}")
    app = window = None
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow()
        window.show()
        app.processEvents()
        window.shutdown()
        window.close()
        app.processEvents()
    except Exception as error:  # noqa: BLE001
        log.exception("selftest: the main window failed to start")
        problems.append(f"main window failed to start: {error}")
    if app is not None:
        _destroy_ui(app, window)
        window = None
    for problem in problems:
        log.error("selftest: %s", problem)
        print(f"SELFTEST FAILED: {problem}", file=sys.stderr)
    if not problems:
        log.info("selftest passed")
        print("SELFTEST OK")
    return 1 if problems else 0


def main():
    log_path = configure_logging()
    install_exception_hooks()
    log = get_logger("app")
    log.info("%s %s starting (log: %s)", APP_NAME, APP_VERSION, log_path)

    if "--selftest" in sys.argv:
        return _selftest(log)

    # The resident hotkey helper launches NEXUS with --activate. If NEXUS is
    # already running, activate that instance instead of creating a second one.
    activate_requested = "--activate" in sys.argv

    mutex, is_first_instance = _single_instance()
    if not is_first_instance:
        if activate_requested and _activate_existing_nexus():
            log.info("Existing NEXUS instance activated.")
        else:
            log.info("NEXUS is already running.")
        return 0

    background_mode = "--background" in sys.argv
    setup_only = "--setup-dependencies" in sys.argv

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Segoe UI", 10))

    # The theme (dark, light or follow Windows) and accent apply to every window, including
    # the first-run wizard, so it is installed on the application before anything is shown.
    settings_for_theme = NEXUSSettings()
    nexus_theme().apply(app, mode=str(settings_for_theme.get("ui_theme", "dark") or "dark"),
                        accent=str(settings_for_theme.get("ui_accent", "#45d9ff") or "#45d9ff"))

    # The same orb as the sidebar logo, in the user's accent colour (assets/nexus.ico, made
    # from the same drawing, is used for the .exe and the installer).
    from ui.brand import app_icon

    nexus_icon = app_icon(str(settings_for_theme.get("ui_accent", "#45d9ff") or "#45d9ff"))
    if nexus_icon.isNull():
        nexus_icon = QIcon(str(resource_path("assets/nexus.ico")))
    app.setWindowIcon(nexus_icon)

    settings = NEXUSSettings()

    # ---------------------------------------------------------
    # First-run setup (interactive launches only)
    # ---------------------------------------------------------
    if not background_mode and not setup_only and not settings.first_run_completed:
        _show_first_run_wizard(settings, log)

    # ---------------------------------------------------------
    # Optional resident Ctrl+Alt+N helper (opt-in)
    # ---------------------------------------------------------
    if settings.global_hotkey_enabled:
        _start_hotkey_helper()

    # ---------------------------------------------------------
    # Local AI preparation: only when local AI can be used
    # ---------------------------------------------------------
    dependencies_ok, dependency_detail = True, ""
    if settings.ai_engine != "online" or setup_only:
        dependencies_ok, dependency_detail = _prepare_dependencies(app, show_dialog=not background_mode)
        log.info("local AI preparation: ok=%s detail=%s", dependencies_ok, dependency_detail)

    if setup_only:
        print(dependency_detail)
        return 0 if dependencies_ok else 1

    window = MainWindow()
    window.setWindowIcon(nexus_icon)

    # ---------------------------------------------------------
    # Legacy background voice (explicit opt-in only; see Settings)
    # ---------------------------------------------------------
    background_voice = NexusBackgroundVoice(
        command_engine=window.command_engine,
        on_activate=window.activate_nexus,
        on_status=lambda message: log.info("voice: %s", message),
    )
    window.set_background_voice(background_voice)
    background_voice.start()  # does nothing unless the user enabled the legacy option
    app.aboutToQuit.connect(background_voice.stop)

    # ---------------------------------------------------------
    # System tray (reminders keep notifying while the window is closed)
    # ---------------------------------------------------------
    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(nexus_icon, parent=app)
        tray.setToolTip("NEXUS - personal desktop assistant")
        tray_menu = QMenu()
        tray_menu.addAction("Open NEXUS").triggered.connect(window.activate_nexus)
        tray_menu.addSeparator()
        tray_menu.addAction("Exit NEXUS").triggered.connect(window.request_quit)
        tray.setContextMenu(tray_menu)
        tray.activated.connect(
            lambda reason: window.activate_nexus()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        tray.show()
        app.aboutToQuit.connect(tray.hide)
    else:
        log.warning("No system tray is available; closing the window will exit NEXUS.")
    window.set_tray(tray)
    app.aboutToQuit.connect(window.shutdown)

    hide_to_tray = tray is not None and tray.isVisible() and (background_mode or settings.start_minimized)
    if hide_to_tray and not activate_requested:
        log.info("Starting hidden in the system tray.")
        window.hide()
    else:
        window.show()
        if activate_requested:
            QTimer.singleShot(80, window.activate_nexus)

    log.info("NEXUS ready.")
    exit_code = app.exec()
    _ = mutex  # keep the single-instance mutex alive until the Qt loop ends
    _destroy_ui(app, window, tray)  # widgets must go before the QApplication (see _destroy_ui)
    window = tray = None
    log.info("NEXUS exited with code %s", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
