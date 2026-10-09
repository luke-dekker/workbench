"""wb: the workbench command line.

  wb list                         projects, kinds, tags
  wb tools <project>              tools a project offers
  wb open <project> <tool> [args] launch a tool on a project
  wb new <project> [--kind K]     create a project root (+ marimo/pluto/julia scaffolding)
  wb doctor                       check every app/executable the registry points at
  wb gui                          the launcher window (what the taskbar button opens)
  wb shortcut [--tray]            Start-menu shortcut for the window (pin it to the taskbar)
  wb sleuth [project] [--apply]   find where a project writes outputs; suggest [artifacts] lines
  wb unity <project> setup|build|deploy|run   headless Unity (docs/FAST_LOOP.md)
  wb tray                         optional system-tray variant
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import launch as L
from . import registry as R


def cmd_list(reg: R.Registry, a) -> int:
    width = max(len(n) for n in reg.projects)
    for name, p in reg.projects.items():
        mark = " " if p.exists else "!"
        tags = ",".join(p.tags)
        print(f"{mark} {name:<{width}}  {p.kind:<7} {tags:<14} {p.root}")
    missing = [n for n, p in reg.projects.items() if not p.exists]
    if missing:
        print(f"\n! root missing: {', '.join(missing)}  (wb new <name> creates it)")
    return 0


def cmd_tools(reg: R.Registry, a) -> int:
    p = reg.project(a.project)
    for t in p.tools:
        src = "command" if t in p.commands else "builtin"
        print(f"{t:<10} {src}")
    return 0


def cmd_open(reg: R.Registry, a) -> int:
    p = reg.project(a.project)
    tool = a.tool or (p.tools[0] if p.tools else "code")
    argv = L.launch(p, reg, tool, a.args)
    print(f"[{p.name}:{tool}] {' '.join(argv)}")
    return 0


MARIMO_STUB = '''import marimo

__generated_with = "0.25.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md("# {name}")
    return


if __name__ == "__main__":
    app.run()
'''


def cmd_new(reg: R.Registry, a) -> int:
    name = a.project
    if name in reg.projects:
        p = reg.projects[name]
        kind = a.kind or p.kind
    else:
        base = Path(reg.defaults.get("notebooks_dir", Path.home() / "workbench/notebooks"))
        p = R.Project(name=name, root=base / name, kind=a.kind or "python")
        kind = p.kind
        print(f"(not in registry; add a [projects.{name}] block to {reg.path})")
    p.root.mkdir(parents=True, exist_ok=True)
    if kind == "python":
        if not (p.root / "pyproject.toml").exists():
            subprocess.run(["uv", "init", "--bare", "--name", name.replace("-", "_")], cwd=p.root, check=False)
        nb = p.root / "notebook.py"
        if not nb.exists():
            nb.write_text(MARIMO_STUB.replace("{name}", name))
    elif kind == "julia":
        if not (p.root / "Project.toml").exists():
            subprocess.run(["julia", "-e", f'using Pkg; Pkg.activate("{p.root.as_posix()}"); Pkg.instantiate()'],
                           check=False)
    elif kind == "octave":
        (p.root / "main.m").touch()
    elif kind == "godot":
        (p.root / "project.godot").touch()
    elif kind == "unity":
        from . import unity as U
        rc = U.scaffold(p, reg, run_setup=not a.no_setup)
        if rc != 0:
            print(f"wb: Unity setup exited {rc}; fix and rerun `wb unity {name} setup`", file=sys.stderr)
            return rc
    print(f"created {p.root} ({kind})")
    return 0


def cmd_unity(reg: R.Registry, a) -> int:
    """Blocking headless Unity runs; `wb open <project> setup|build|deploy` opens these in a terminal tab."""
    from . import unity as U
    p = reg.project(a.project)
    if a.action == "setup":
        if not (p.root / "ProjectSettings").exists():
            return U.scaffold(p, reg, run_setup=True)
        return U.headless(p, reg, "Workbench.Setup.Headless", quit_flag=False)
    if a.action == "build":
        U.build(p, reg, a.platform or "android", release=a.release)
        return 0
    if a.action == "deploy":
        return U.deploy(p, reg, skip_build=a.skip_build)
    if a.action == "run":   # any static method, e.g. wb unity unity-app run My.Editor.Method
        return U.headless(p, reg, a.platform, quit_flag=True)
    return 1


def cmd_doctor(reg: R.Registry, a) -> int:
    ok = True

    def check(label: str, found: bool, where: str = "") -> None:
        nonlocal ok
        ok &= found
        print(f"{'ok ' if found else 'MISSING'} {label:<12} {where}")

    for exe in ("uv", "python", "julia", "juliaup", "jupyter", "marimo", "code", "wt", "git"):
        w = shutil.which(exe)
        check(exe, bool(w), w or "")
    for key in ("godot", "unity_hub", "blender"):
        path = reg.apps.get(key, "")
        check(key, Path(path).exists(), path)
    ed = Path(reg.apps.get("unity_editors", ""))
    versions = [d.name for d in ed.iterdir()] if ed.exists() else []
    check("unity", bool(versions), ", ".join(versions))
    oc = L.find_octave(reg)
    check("octave", bool(oc), oc or "")
    # Julia shared env + kernels
    env = reg.apps.get("julia_env", "@notebooks")
    r = subprocess.run(["julia", f"--project={env}", "-e", "import Pluto, IJulia; print(\"pluto+ijulia\")"],
                       capture_output=True, text=True)
    check("pluto", r.returncode == 0, r.stdout.strip() or r.stderr.strip()[:80])
    if shutil.which("jupyter"):
        r = subprocess.run(["jupyter", "kernelspec", "list"], capture_output=True, text=True)
        kernels = [ln.split()[0] for ln in r.stdout.splitlines()[1:] if ln.strip()]
        check("kernels", bool(kernels), ", ".join(kernels))
    return 0 if ok else 1


APP_ID = "Workbench.Launcher"


def cmd_shortcut(reg: R.Registry, a) -> int:
    """Start-menu shortcut for the window.

    Targets the *base* pythonw.exe (the uv venv's pythonw is a trampoline that spawns it, so the
    window would otherwise belong to a different exe than the pinned button). The window only
    needs the stdlib, and `-m wb.launcher` finds `wb` via the working directory. The shortcut
    and the process also share an explicit AppUserModelID so Windows shows one taskbar button.
    """
    tray = getattr(a, "tray", False)
    if tray:
        pythonw = Path(sys.executable).with_name("pythonw.exe")   # tray needs pystray from the tool env
    else:
        pythonw = Path(sys.base_prefix) / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    args = "-m wb.tray" if tray else "-m wb.launcher"
    workdir = str(reg.path.parent)
    icon = reg.path.parent / "assets" / "workbench.ico"
    lnk = Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Workbench.lnk"
    ps = f"""
$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}')
$s.TargetPath = '{pythonw}'
$s.Arguments = '{args}'
$s.WorkingDirectory = '{workdir}'
$s.Description = 'Workbench launcher'
{"$s.IconLocation = '" + str(icon) + "'" if icon.exists() else ""}
$s.Save()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    marker = reg.path.parent / "assets" / ".aumid"
    if not tray and _set_shortcut_app_id(lnk, APP_ID):
        marker.write_text(APP_ID, encoding="utf-8")
        ident = f"AppUserModelID {APP_ID} set on shortcut and window"
    else:
        marker.unlink(missing_ok=True)
        ident = "grouping by exe path (pywin32 not available for AppUserModelID)"
    print(f"shortcut: {lnk}\n  target: {pythonw} {args}\n  {ident}\nRight-click it in the Start menu > Pin to taskbar.")
    return 0


def _set_shortcut_app_id(lnk: Path, app_id: str) -> bool:
    """Write System.AppUserModel.ID into the .lnk's property store (needs pywin32)."""
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon
    except ImportError:
        return False
    try:
        store = propsys.SHGetPropertyStoreFromParsingName(str(lnk), None, 2, propsys.IID_IPropertyStore)  # GPS_READWRITE
        store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(app_id, pythoncom.VT_LPWSTR))
        store.Commit()
        return True
    except Exception as e:  # pragma: no cover
        print(f"  (could not set AppUserModelID: {e})")
        return False


def cmd_tray(reg: R.Registry, a) -> int:
    from . import tray
    return tray.main()


def cmd_gui(reg: R.Registry, a) -> int:
    from . import launcher
    return launcher.main()


def cmd_sleuth(reg: R.Registry, a) -> int:
    from . import sleuth as S
    names = [a.project] if a.project else [n for n, p in reg.projects.items() if p.exists]
    for name in names:
        rep = S.sleuth(reg.project(name), reg)
        print(S.format_report(rep))
        print()
        if a.apply and rep.root.exists():
            block = "\n# --- wb sleuth suggestion (review, uncomment what is right) ---\n"
            block += "\n".join("# " + ln for ln in rep.suggestion().splitlines()) + "\n"
            with open(reg.path, "a", encoding="utf-8") as f:
                f.write(block)
            print(f"appended commented suggestion for {name} to {reg.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("tools"); s.add_argument("project"); s.set_defaults(fn=cmd_tools)
    s = sub.add_parser("open"); s.add_argument("project"); s.add_argument("tool", nargs="?")
    s.add_argument("args", nargs=argparse.REMAINDER); s.set_defaults(fn=cmd_open)
    s = sub.add_parser("new"); s.add_argument("project"); s.add_argument("--kind", choices=["python", "julia", "octave", "godot", "unity"])
    s.add_argument("--no-setup", action="store_true", help="unity: scaffold only, skip the headless Setup pass")
    s.set_defaults(fn=cmd_new)
    s = sub.add_parser("unity", help="headless Unity: setup | build [android|windows] | deploy | run <Method>")
    s.add_argument("project"); s.add_argument("action", choices=["setup", "build", "deploy", "run"])
    s.add_argument("platform", nargs="?", help="build: android (default) | windows; run: the static method")
    s.add_argument("--release", action="store_true", help="build: non-development build")
    s.add_argument("--skip-build", action="store_true", help="deploy: install the last build instead of rebuilding")
    s.set_defaults(fn=cmd_unity)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    s = sub.add_parser("shortcut"); s.add_argument("--tray", action="store_true", help="shortcut runs the tray instead of the window")
    s.set_defaults(fn=cmd_shortcut)
    sub.add_parser("tray").set_defaults(fn=cmd_tray)
    sub.add_parser("gui").set_defaults(fn=cmd_gui)
    s = sub.add_parser("sleuth", help="find where a project writes outputs; suggest [artifacts] lines")
    s.add_argument("project", nargs="?"); s.add_argument("--apply", action="store_true",
                                                         help="append the suggestion (commented) to workbench.toml")
    s.set_defaults(fn=cmd_sleuth)
    a = ap.parse_args(argv)
    reg = R.load()
    try:
        return a.fn(reg, a)
    except (L.LaunchError, KeyError) as e:
        print(f"wb: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
