"""Tool launchers. Each launcher returns the argv it started (for logging/tests)."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
from pathlib import Path

from .registry import Project, Registry

IS_WIN = os.name == "nt"
DETACH = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if IS_WIN else 0
NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE if IS_WIN else 0


class LaunchError(RuntimeError):
    pass


# ----------------------------------------------------------------- helpers
def _spawn(argv: list[str], cwd: Path | None = None) -> list[str]:
    """Start a GUI process detached from this console."""
    subprocess.Popen(
        argv, cwd=str(cwd) if cwd else None, creationflags=DETACH,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return argv


def _in_terminal(cmdline: str, cwd: Path, title: str) -> list[str]:
    """Run a shell command in a new Windows Terminal tab (falls back to a console window)."""
    ps = ["powershell", "-NoExit", "-Command", cmdline] if cmdline else ["powershell", "-NoExit"]
    if shutil.which("wt"):
        argv = ["wt", "-w", "0", "new-tab", "--title", title, "-d", str(cwd), *ps]
    else:
        argv = ["cmd", "/c", "start", title, *ps]
    subprocess.Popen(argv, cwd=str(cwd), creationflags=NEW_CONSOLE)
    return argv


def has_uv_project(p: Project) -> bool:
    return (p.root / "pyproject.toml").exists() or (p.root / ".venv").exists()


WORKBENCH_ROOT = Path(__file__).resolve().parent.parent


def _uv_prefix(*pkgs: str) -> str:
    """`uv run` inside the project's env, with extra packages layered on.

    Always layers the workbench package itself (editable) so `from wb import catalog`
    works in any project's notebook; its core deps are deliberately small.
    """
    withs = " ".join(f"--with {x}" for x in pkgs)
    return f'uv run --with-editable "{WORKBENCH_ROOT}" {withs}'.strip()


def find_octave(reg: Registry) -> str | None:
    cfg = reg.apps.get("octave", "auto")
    if cfg != "auto" and Path(cfg).exists():
        return cfg
    # octave-launch.exe sets up the MSYS environment; prefer it over the raw binaries.
    patterns = [
        str(Path.home() / "AppData/Local/Programs/GNU Octave/*/octave-launch.exe"),
        "C:/Program Files/GNU Octave/*/octave-launch.exe",
        str(Path.home() / "AppData/Local/Programs/GNU Octave/*/mingw64/bin/octave-gui.exe"),
        "C:/Program Files/GNU Octave/*/mingw64/bin/octave-gui.exe",
    ]
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return shutil.which("octave-gui") or shutil.which("octave")


def unity_exe(reg: Registry, version: str) -> Path:
    return Path(reg.apps["unity_editors"]) / version / "Editor" / "Unity.exe"


def unity_project_version(root: Path) -> str | None:
    f = root / "ProjectSettings" / "ProjectVersion.txt"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.startswith("m_EditorVersion:"):
                return line.split(":", 1)[1].strip()
    return None


# ---------------------------------------------------------------- launchers
def code(p: Project, reg: Registry, args: list[str]) -> list[str]:
    exe = shutil.which("code") or "code"
    return _spawn([exe, str(p.root), *args])


def term(p: Project, reg: Registry, args: list[str]) -> list[str]:
    return _in_terminal(" ".join(args), p.root, p.name)


def explorer(p: Project, reg: Registry, args: list[str]) -> list[str]:
    return _spawn(["explorer", str(p.root)])


LOG_DIR = WORKBENCH_ROOT / "logs"
RUNNING: list[tuple[str, subprocess.Popen]] = []   # notebook servers started by this process


def _uv_argv(*pkgs: str) -> list[str]:
    argv = ["uv", "run", "--with-editable", str(WORKBENCH_ROOT)]
    for x in pkgs:
        argv += ["--with", x]
    return argv


def julia_env() -> dict:
    """Environment that points PythonCall at the workbench venv (so `using Workbench` works)."""
    env = os.environ.copy()
    env["JULIA_PYTHONCALL_EXE"] = str(WORKBENCH_ROOT / ".venv" / "Scripts" / "python.exe")
    env["JULIA_CONDAPKG_BACKEND"] = "Null"
    return env


def _server(argv: list[str], cwd: Path, title: str, reg: Registry | None = None,
            env: dict | None = None) -> list[str]:
    """Start a notebook server (marimo / jupyter / Pluto). They open the browser themselves.

    Default: hidden, no console, output appended to logs/<title>.log, tracked in RUNNING so the
    window can stop them. Set `servers = "terminal"` under [defaults] to get a Windows Terminal
    tab instead (visible logs, Ctrl-C to stop).
    """
    mode = (reg.defaults.get("servers") if reg else None) or "hidden"
    if mode == "terminal":
        return _in_terminal(subprocess.list2cmdline(argv), cwd, title)
    LOG_DIR.mkdir(exist_ok=True)
    log = open(LOG_DIR / f"{_slug(title)}.log", "ab")
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if IS_WIN else 0
    proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    RUNNING.append((title, proc))
    return argv


def running_servers() -> list[tuple[str, subprocess.Popen]]:
    RUNNING[:] = [(t, pr) for t, pr in RUNNING if pr.poll() is None]
    return list(RUNNING)


def stop_servers() -> int:
    """Kill every tracked server and its children (uv run -> python -> marimo)."""
    n = 0
    for title, proc in running_servers():
        if IS_WIN:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.terminate()
        n += 1
    RUNNING.clear()
    return n


def marimo(p: Project, reg: Registry, args: list[str]) -> list[str]:
    """marimo edit, inside the project's uv env when there is one (so torch etc. match)."""
    extras = reg.defaults.get("marimo_extras", [])
    if not args:
        # no file given: marimo's home over the project's notebooks folder, not the whole repo
        nbdir = p.root / NOTEBOOK_DIR
        nbdir.mkdir(exist_ok=True)
        args = [str(nbdir)]
    if has_uv_project(p):
        argv = _uv_argv("marimo", *extras) + ["marimo", "edit", "--no-token", *args]
    else:
        argv = ["marimo", "edit", "--no-token", *args]   # global `uv tool install marimo`
    return _server(argv, p.root, f"marimo-{p.name}", reg)


def jupyter(p: Project, reg: Registry, args: list[str]) -> list[str]:
    if has_uv_project(p):
        argv = _uv_argv("jupyterlab") + ["jupyter", "lab", *args]
    else:
        argv = ["jupyter", "lab", *args]
    return _server(argv, p.root, f"jupyter-{p.name}", reg)


def julia_env_prefix() -> str:
    """PowerShell prefix that points PythonCall at the workbench venv, so `using Workbench`
    (julia/Workbench) reaches wb.catalog without CondaPkg downloading its own Python."""
    py = WORKBENCH_ROOT / ".venv" / "Scripts" / "python.exe"
    return f"$env:JULIA_PYTHONCALL_EXE='{py}'; $env:JULIA_CONDAPKG_BACKEND='Null'; "


def pluto(p: Project, reg: Registry, args: list[str]) -> list[str]:
    env = reg.apps.get("julia_env", "@notebooks")
    argv = ["julia", f"--project={env}", "-e", "using Pluto; Pluto.run()"]
    return _server(argv, p.root, f"pluto-{p.name}", reg, env=julia_env())


def julia(p: Project, reg: Registry, args: list[str]) -> list[str]:
    if (p.root / "Project.toml").exists():
        proj = str(p.root)
    else:
        proj = reg.apps.get("julia_env", "@notebooks")
    cmd = julia_env_prefix() + f'julia --project="{proj}" {" ".join(args)}'.strip()
    return _in_terminal(cmd, p.root, f"julia:{p.name}")


def octave(p: Project, reg: Registry, args: list[str]) -> list[str]:
    exe = find_octave(reg)
    if not exe:
        raise LaunchError("Octave not found; install with `winget install GNU.Octave`, then `wb doctor`")
    return _spawn([exe, "--gui", *args], cwd=p.root)


def godot(p: Project, reg: Registry, args: list[str]) -> list[str]:
    exe = reg.apps["godot"]
    gdir = p.godot_dir or p.root
    if (gdir / "project.godot").exists():
        return _spawn([exe, "--path", str(gdir), "-e", *args])
    return _spawn([exe, "-p", *args])  # project manager


def godot_project_dir(path: Path) -> Path | None:
    """Nearest ancestor holding project.godot (the Godot project a .tscn belongs to)."""
    for d in (path if path.is_dir() else path.parent, *path.parents):
        if (d / "project.godot").exists():
            return d
    return None


def godot_run(p: Project, reg: Registry, args: list[str]) -> list[str]:
    """Run a scene (or the main scene) directly: `godot --path <proj> [scene]`, no editor.

    args[0] may be a .tscn path, relative to the Godot project dir or to the project root."""
    exe = reg.apps["godot"]
    gdir = p.godot_dir or p.root
    scene: Path | None = None
    if args and args[0].endswith(".tscn"):
        cand = Path(args[0])
        for base in (gdir, p.root, Path.cwd()):
            if (base / cand).exists():
                scene = (base / cand).resolve()
                break
        if scene is None:
            raise LaunchError(f"scene not found: {args[0]}")
        gdir = godot_project_dir(scene) or gdir
        args = args[1:]
    if not (gdir / "project.godot").exists():
        raise LaunchError(f"{p.name}: no project.godot under {gdir}")
    argv = [exe, "--path", str(gdir)]
    if scene is not None:
        argv.append("res://" + scene.relative_to(gdir).as_posix())
    return _spawn(argv + list(args), cwd=gdir)


def unity(p: Project, reg: Registry, args: list[str]) -> list[str]:
    version = unity_project_version(p.root) or p.extra.get("unity_version")
    if not version:
        raise LaunchError(f"{p.name}: no ProjectSettings/ProjectVersion.txt and no unity_version in registry")
    exe = unity_exe(reg, version)
    if not exe.exists():
        raise LaunchError(f"Unity {version} not installed at {exe}; open unity_hub to add it")
    return _spawn([str(exe), "-projectPath", str(p.root), *args])


def unity_hub(p: Project, reg: Registry, args: list[str]) -> list[str]:
    return _spawn([reg.apps["unity_hub"]])


def _wb_in_terminal(p: Project, words: list[str], title: str) -> list[str]:
    """Run `wb <words>` in a Windows Terminal tab (headless Unity runs are long; keep the window free)."""
    wb = shutil.which("wb")
    cmd = subprocess.list2cmdline([wb or "wb", *words]) if wb else \
        subprocess.list2cmdline(["uv", "run", "--directory", str(WORKBENCH_ROOT), "wb", *words])
    return _in_terminal(cmd, p.root, title)


def unity_setup(p: Project, reg: Registry, args: list[str]) -> list[str]:
    return _wb_in_terminal(p, ["unity", p.name, "setup", *args], f"setup:{p.name}")


def unity_build(p: Project, reg: Registry, args: list[str]) -> list[str]:
    return _wb_in_terminal(p, ["unity", p.name, "build", *args], f"build:{p.name}")


def unity_deploy(p: Project, reg: Registry, args: list[str]) -> list[str]:
    return _wb_in_terminal(p, ["unity", p.name, "deploy", *args], f"deploy:{p.name}")


def blender(p: Project, reg: Registry, args: list[str]) -> list[str]:
    return _spawn([reg.apps["blender"], *args], cwd=p.root)


# ----------------------------------------------------------- project notebooks
SKIP_DIRS = {".venv", "venv", "node_modules", ".git", "__pycache__", "dist", "build",
             "__marimo__", ".ipynb_checkpoints", "runs", "data", "demo_data", "snippets",
             ".godot", "addons", "Library", "Temp", "Obj", "Builds", "Logs", "UserSettings", "Packages"}
NOTEBOOK_DIR = "notebooks"
NOTEBOOK_SUFFIXES = (".py", ".ipynb", ".jl", ".m", ".tscn")


def notebook_kind(path: Path) -> str | None:
    """marimo / jupyter / pluto / octave / scene (Godot .tscn, runnable), or None."""
    suf = path.suffix.lower()
    try:
        if suf == ".ipynb":
            return "jupyter"
        if suf == ".tscn":
            return "scene"
        if suf == ".py":
            head = path.read_text(encoding="utf-8", errors="ignore")[:4000]
            # a marimo notebook's first real statement is `import marimo` (PEP 723 header comments allowed);
            # merely containing "marimo.App(" is not enough (wb/cli.py holds the stub as a string)
            first = next((ln for ln in head.splitlines() if ln.strip() and not ln.lstrip().startswith("#")), "")
            return "marimo" if first.startswith("import marimo") and "marimo.App(" in head else None
        if suf == ".jl":
            head = path.read_text(encoding="utf-8", errors="ignore")[:200]
            return "pluto" if "A Pluto.jl notebook" in head else None
        if suf == ".m":
            return "octave"
    except OSError:
        return None
    return None


def find_notebooks(p: Project, max_depth: int = 3) -> list[tuple[Path, str]]:
    """Notebooks under the project root, shallowest first."""
    found: list[tuple[Path, str]] = []
    if not p.root.exists():
        return found

    def walk(d: Path, depth: int) -> None:
        try:
            entries = sorted(d.iterdir(), key=lambda e: (e.is_dir(), e.name.lower()))
        except OSError:
            return
        for e in entries:
            if e.is_dir():
                if depth < max_depth and e.name not in SKIP_DIRS and not e.name.startswith("."):
                    walk(e, depth + 1)
            elif e.suffix.lower() in NOTEBOOK_SUFFIXES:
                k = notebook_kind(e)
                if k:
                    found.append((e, k))

    walk(p.root, 0)
    return found


def package_name(p: Project) -> str | None:
    """Importable package for a python project, if we can tell: a dir named after pyproject's name."""
    py = p.root / "pyproject.toml"
    if not py.exists():
        return None
    import tomllib
    try:
        name = tomllib.loads(py.read_text(encoding="utf-8")).get("project", {}).get("name")
    except (tomllib.TOMLDecodeError, OSError):
        return None
    if not name:
        return None
    for cand in (name, name.replace("-", "_")):
        if (p.root / cand / "__init__.py").exists() or (p.root / "src" / cand / "__init__.py").exists():
            return cand
    return None


PROJECT_MARIMO_STUB = '''import marimo

__generated_with = "0.25.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[1]   # {project} root
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return ROOT, mo
{import_cell}

@app.cell
def _(ROOT, mo):
    mo.md(f"""
    # {name}

    project **{project}** at `{ROOT}`
    """)
    return


@app.cell
def _():
    # What data this project has. Nothing is loaded until you call catalog.load(...)
    from wb import catalog
    catalog.show("{project}")
    return (catalog,)


if __name__ == "__main__":
    app.run()
'''

IMPORT_CELL = '''

@app.cell
def _():
    import {pkg}
    return ({pkg},)
'''

PLUTO_STUB = '''### A Pluto.jl notebook ###
# v0.20.0

using Markdown
using InteractiveUtils

# ╔═╡ {cell}
md"# {name}"

# ╔═╡ {cell2}
# What data this project has. Nothing is loaded until you call Workbench.load(...)
using Workbench

# ╔═╡ {cell3}
Workbench.show("{project}")

# ╔═╡ Cell order:
# ╠═{cell}
# ╠═{cell2}
# ╠═{cell3}
'''


def _slug(name: str) -> str:
    import re
    from datetime import datetime
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    return s or datetime.now().strftime("nb_%Y%m%d_%H%M%S")


def new_notebook(p: Project, reg: Registry, kind: str, name: str) -> list[str]:
    """Create <root>/notebooks/<name>.<ext> for kind in marimo|pluto|jupyter and open it.
    Scratch projects whose root already lives under the notebooks dir get the file at the root."""
    scratch_base = Path(reg.defaults.get("notebooks_dir", ""))
    d = p.root if (scratch_base and p.root.is_relative_to(scratch_base)) else p.root / NOTEBOOK_DIR
    d.mkdir(parents=True, exist_ok=True)
    if kind == "marimo":
        f = d / f"{_slug(name)}.py"
        if not f.exists():
            pkg = package_name(p)
            body = PROJECT_MARIMO_STUB.replace("{project}", p.name).replace("{name}", name or f.stem)
            body = body.replace("{import_cell}", IMPORT_CELL.replace("{pkg}", pkg) if pkg else "")
            f.write_text(body, encoding="utf-8")
    elif kind == "pluto":
        import uuid
        f = d / f"{_slug(name)}.jl"
        if not f.exists():
            body = PLUTO_STUB.replace("{name}", name or f.stem).replace("{project}", p.name)
            for key in ("{cell}", "{cell2}", "{cell3}"):
                body = body.replace(key, str(uuid.uuid4()))
            f.write_text(body, encoding="utf-8")
    elif kind == "jupyter":
        import json
        f = d / f"{_slug(name)}.ipynb"
        if not f.exists():
            nb = {"cells": [{"cell_type": "markdown", "metadata": {}, "source": [f"# {name or f.stem}"]},
                            {"cell_type": "code", "metadata": {}, "source": [], "outputs": [], "execution_count": None}],
                  "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
                  "nbformat": 4, "nbformat_minor": 5}
            f.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    else:
        raise LaunchError(f"unknown notebook kind {kind!r}")
    return open_notebook(p, reg, f)


def open_notebook(p: Project, reg: Registry, path: Path) -> list[str]:
    kind = notebook_kind(path)
    rel = path.relative_to(p.root) if path.is_relative_to(p.root) else path
    if kind == "marimo":
        return marimo(p, reg, [str(path)])
    if kind == "jupyter":
        return jupyter(p, reg, [str(path)])
    if kind == "pluto":
        env = reg.apps.get("julia_env", "@notebooks")
        # the path travels as its own argv entry (ARGS[1]); no shell, so no quoting games
        argv = ["julia", f"--project={env}", "-e", "using Pluto; Pluto.run(notebook=ARGS[1])", path.as_posix()]
        return _server(argv, p.root, f"pluto-{p.name}", reg, env=julia_env())
    if kind == "octave":
        exe = find_octave(reg)
        if not exe:
            raise LaunchError("Octave not found")
        return _spawn([exe, "--gui", "--persist", str(path)], cwd=path.parent)
    if kind == "scene":
        return godot_run(p, reg, [str(path)])
    raise LaunchError(f"{rel} is not a notebook I recognise")


def command(name: str):
    """Launcher for a per-project [projects.X.commands] entry."""
    def run(p: Project, reg: Registry, args: list[str]) -> list[str]:
        if name not in p.commands:
            raise LaunchError(f"{p.name} has no command {name!r}")
        cmd = p.expand(p.commands[name])
        if args:
            cmd += " " + " ".join(args)
        return _in_terminal(cmd, p.root, f"{name}:{p.name}")
    return run


BUILTIN = {
    "code": code, "term": term, "explorer": explorer,
    "marimo": marimo, "jupyter": jupyter, "pluto": pluto, "julia": julia, "octave": octave,
    "godot": godot, "godot_run": godot_run, "unity": unity, "unity_hub": unity_hub, "blender": blender,
    "setup": unity_setup, "build": unity_build, "deploy": unity_deploy,
}


def resolve(p: Project, tool: str):
    if tool in p.commands:
        return command(tool)
    if tool in BUILTIN:
        return BUILTIN[tool]
    raise LaunchError(f"unknown tool {tool!r}; project {p.name} offers: {', '.join(p.tools)}")


def launch(p: Project, reg: Registry, tool: str, args: list[str] | None = None) -> list[str]:
    if not p.exists and tool != "unity_hub":
        raise LaunchError(f"{p.name}: root {p.root} does not exist (try `wb new {p.name}`)")
    return resolve(p, tool)(p, reg, args or [])
