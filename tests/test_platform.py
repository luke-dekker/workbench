"""Every wb module imports on every platform; the Windows-only paths run only on Windows."""
from __future__ import annotations

import importlib
import sys

import pytest

from wb import launch as L

WINDOWS = sys.platform == "win32"
windows_only = pytest.mark.skipif(not WINDOWS, reason="needs Windows (Windows Terminal, taskkill, winreg, pywin32)")


@pytest.mark.parametrize("mod", ["wb", "wb.registry", "wb.catalog", "wb.launch", "wb.sleuth", "wb.cli",
                                 "wb.unity", "wb.launcher", "wb.tray"])
def test_module_imports_anywhere(mod):
    importlib.import_module(mod)


# ------------------------------------------------------- pure functions
def test_launch_flags_match_platform():
    assert L.IS_WIN == WINDOWS
    if not WINDOWS:
        assert L.DETACH == 0 and L.NEW_CONSOLE == 0


def test_julia_env_points_at_workbench_venv():
    env = L.julia_env()
    assert env["JULIA_CONDAPKG_BACKEND"] == "Null"
    assert env["JULIA_PYTHONCALL_EXE"] == str(L.WORKBENCH_ROOT / ".venv" / "Scripts" / "python.exe")
    assert "JULIA_PYTHONCALL_EXE" in L.julia_env_prefix()


def test_in_terminal_argv(no_spawn, tmp_path, monkeypatch):
    monkeypatch.setattr(L.shutil, "which", lambda name: None)
    argv = L._in_terminal("echo hi", tmp_path, "title")
    assert argv == ["cmd", "/c", "start", "title", "powershell", "-NoExit", "-Command", "echo hi"]
    assert L._in_terminal("", tmp_path, "t")[-2:] == ["powershell", "-NoExit"]
    monkeypatch.setattr(L.shutil, "which", lambda name: "wt" if name == "wt" else None)
    argv = L._in_terminal("echo hi", tmp_path, "title")
    assert argv[:6] == ["wt", "-w", "0", "new-tab", "--title", "title"]
    assert argv[argv.index("-d") + 1] == str(tmp_path)


def test_tray_helpers_off_windows():
    from wb import tray
    assert tray.MUTEX_NAME.startswith("Local\\")
    if not WINDOWS:
        assert tray._single_instance() is True
        assert tray.promote_tray_icon() is False
        tray._message_box("x")                                        # no-op


def test_tray_main_without_extra(monkeypatch, capsys):
    from wb import tray
    monkeypatch.setattr(tray, "pystray", None)
    assert tray.main() == 1
    assert "pystray" in capsys.readouterr().err


def test_launcher_main_without_tk(monkeypatch):
    from wb import launcher
    monkeypatch.setattr(launcher, "tk", None)
    with pytest.raises(L.LaunchError, match="tkinter"):
        launcher.main()


def test_launcher_constants():
    from wb import launcher
    assert launcher.APP_ID == "Workbench.Launcher"
    assert set(launcher.KIND_LABEL) == {"marimo", "jupyter", "pluto", "octave", "scene"}
    assert [k for k, _ in launcher.NEW_KINDS] == ["marimo", "pluto", "jupyter"]


def test_tray_make_icon():
    from wb import tray
    if tray.Image is None:
        pytest.skip("pillow not installed (tray extra)")
    img = tray.make_icon(32)
    assert img.size == (32, 32) and img.mode == "RGBA"


# ------------------------------------------------------------- Windows
@windows_only
def test_windows_flags():
    import subprocess
    assert L.DETACH == subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    assert L.NEW_CONSOLE == subprocess.CREATE_NEW_CONSOLE


@windows_only
def test_stop_servers_uses_taskkill(synthetic_registry, no_spawn, monkeypatch):
    calls = []
    monkeypatch.setattr(L.subprocess, "run", lambda argv, **kw: calls.append(argv))
    reg = synthetic_registry.reg
    L.jupyter(reg.projects["alpha"], reg, [])
    assert L.stop_servers() == 1
    assert calls and calls[0][:3] == ["taskkill", "/T", "/F"]


@windows_only
def test_reveal_in_explorer(tmp_path, no_spawn, monkeypatch):
    from wb import launcher
    opened = []
    monkeypatch.setattr(launcher.os, "startfile", lambda p: opened.append(p))
    assert launcher._reveal(tmp_path) == ["explorer", str(tmp_path)]
    assert opened == [str(tmp_path)]
    f = tmp_path / "f.txt"
    f.write_text("", encoding="utf-8")
    launcher._reveal(f)
    assert no_spawn.calls[-1]["argv"][:2] == ["explorer", "/select,"]


@windows_only
def test_shortcut_app_id_needs_pywin32(tmp_path):
    from wb import cli
    pytest.importorskip("win32com")
    assert cli._set_shortcut_app_id(tmp_path / "missing.lnk", cli.APP_ID) is False
