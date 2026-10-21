"""Consequential PC actions must be confirmed before they run."""
from __future__ import annotations

import pytest

from core.pc_control import PCController


@pytest.fixture()
def pc(tmp_path, monkeypatch):
    controller = PCController()
    controller.user_home = tmp_path.resolve()
    return controller


@pytest.mark.parametrize("command", ["delete file notes.txt", "remove the file notes.txt", "Delete File notes.txt"])
def test_deleting_a_file_asks_first(pc, tmp_path, command):
    question = pc.confirmation_prompt(command.replace("notes.txt", str(tmp_path / "notes.txt")))
    assert question and "Recycle Bin" in question and "notes.txt" in question


@pytest.mark.parametrize("command", [
    "open file notes.txt", "create file x.txt", "rename file a.txt to b.txt", "open calculator", "what time is it", "delete my feelings",
])
def test_harmless_commands_do_not_prompt(pc, command):
    assert pc.confirmation_prompt(command) is None


def test_path_outside_the_user_folder_is_named_and_then_refused(pc):
    question = pc.confirmation_prompt("delete file /etc/passwd")
    assert question and "/etc/passwd" in question
    ok, message = pc.execute("delete file /etc/passwd")
    assert "limited to your user folder" in message


def test_declined_delete_leaves_the_file_in_place(qapp, tmp_path, monkeypatch, track):
    from PySide6.QtWidgets import QMessageBox

    from ui.main_window import MainWindow

    victim = tmp_path / "keep.txt"
    victim.write_text("precious")
    win = track(MainWindow())
    win.command_engine.pc.user_home = tmp_path.resolve()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    win.process_command(f"delete file {victim}")
    assert victim.exists()
    assert any("Nothing was changed" in m["content"] for m in win.conversation_manager.get_messages(win.current_conversation_id))


def test_confirmed_delete_goes_to_the_recycle_bin(qapp, tmp_path, monkeypatch, track):
    from PySide6.QtWidgets import QMessageBox

    from core.pc_control import PCController
    from ui.main_window import MainWindow

    victim = tmp_path / "old.txt"
    victim.write_text("x")
    binned = []
    monkeypatch.setattr(PCController, "_send_to_recycle_bin", staticmethod(lambda path: binned.append(path.name)))
    win = track(MainWindow())
    win.command_engine.pc.user_home = tmp_path.resolve()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win.process_command(f"delete file {victim}")
    assert binned == ["old.txt"]
