"""Taskbar tray launcher: right-click -> project -> tool.

Run with `wb tray` or `pythonw -m wb.tray`. Needs the `tray` extra (pystray, pillow).
Re-reads workbench.toml on every menu open, so registry edits show up live.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    print("wb tray needs: uv tool install --editable . --with pystray --with pillow", file=sys.stderr)
    raise

from . import launch as L
from . import registry as R

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def make_icon(size: int = 64) -> Image.Image:
    """Simple generated glyph: dark rounded square, three colored node dots."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, size - 3, size - 3], radius=size // 6, fill=(28, 30, 36, 255))
    r = size // 8
    for (x, y), col in zip(((0.3, 0.3), (0.7, 0.3), (0.5, 0.7)),
                           ((78, 201, 176), (229, 192, 123), (198, 120, 221))):
        cx, cy = int(x * size), int(y * size)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    d.line([(int(0.3 * size), int(0.3 * size)), (int(0.5 * size), int(0.7 * size)),
            (int(0.7 * size), int(0.3 * size))], fill=(120, 124, 136), width=max(2, size // 24))
    return img


def ensure_ico() -> Path:
    ASSETS.mkdir(exist_ok=True)
    ico = ASSETS / "workbench.ico"
    if not ico.exists():
        make_icon(256).save(ico, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    return ico


def _launch(p: R.Project, reg: R.Registry, tool: str):
    def cb(icon, item):
        try:
            L.launch(p, reg, tool)
        except L.LaunchError as e:
            icon.notify(str(e), title=f"wb: {p.name}")
    return cb


def _edit_registry(icon, item):
    reg = R.load()
    subprocess.Popen(["code", str(reg.path)], shell=True)


def build_menu():
    reg = R.load()
    items = []
    for name, p in reg.projects.items():
        sub = [pystray.MenuItem(t, _launch(p, reg, t)) for t in p.tools]
        if p.exists:
            sub.append(pystray.Menu.SEPARATOR)
            sub.append(pystray.MenuItem("explorer", _launch(p, reg, "explorer")))
        label = name if p.exists else f"{name}  (missing)"
        items.append(pystray.MenuItem(label, pystray.Menu(*sub), enabled=p.exists))
    items += [
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Edit registry", _edit_registry),
        pystray.MenuItem("Quit", lambda icon, item: icon.stop()),
    ]
    return pystray.Menu(*items)


MUTEX_NAME = "Local\\workbench-tray"


def _single_instance() -> bool:
    """Hold a named mutex for the life of the process; False if another tray already has it."""
    if sys.platform != "win32":
        return True
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW(None, False, MUTEX_NAME)
    ERROR_ALREADY_EXISTS = 183
    return k32.GetLastError() != ERROR_ALREADY_EXISTS


def _message_box(text: str, title: str = "Workbench") -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)  # MB_ICONINFORMATION


def promote_tray_icon() -> bool:
    """Windows 11 hides new tray icons behind the ^ chevron. Flip ours to always-visible.

    Windows records tray icons by the real executable path, which for a uv venv is the
    base interpreter's pythonw.exe, so we match on that.
    """
    if sys.platform != "win32":
        return False
    import winreg
    exe = Path(sys.executable).name.lower()
    base_exe = getattr(sys, "_base_executable", sys.executable)
    targets = {str(Path(p)).lower() for p in (sys.executable, base_exe)}
    changed = False
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\NotifyIconSettings")
    except OSError:
        return False
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        try:
            with winreg.OpenKey(root, sub, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                path, _ = winreg.QueryValueEx(k, "ExecutablePath")
                if str(path).lower() in targets or Path(str(path)).name.lower() == exe:
                    try:
                        cur, _ = winreg.QueryValueEx(k, "IsPromoted")
                    except OSError:
                        cur = 0
                    if cur != 1:
                        winreg.SetValueEx(k, "IsPromoted", 0, winreg.REG_DWORD, 1)
                        changed = True
        except OSError:
            continue
    return changed


def _setup(icon: "pystray.Icon") -> None:
    icon.visible = True
    promoted = promote_tray_icon()
    hint = "Icon pinned to the taskbar tray." if promoted else "Look under the ^ chevron if you do not see the icon."
    try:
        icon.notify(f"Right-click the icon for projects. {hint}", "Workbench is running")
    except Exception:
        pass


def main() -> int:
    if not _single_instance():
        _message_box("Workbench is already running. Right-click its icon in the taskbar tray "
                     "(look under the ^ chevron if it is hidden).")
        return 0
    ensure_ico()
    icon = pystray.Icon("workbench", make_icon(), "Workbench", menu=pystray.Menu(lambda: build_menu().items))
    icon.run(setup=_setup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
