"""Unity + Android helpers for the fast loop (see docs/FAST_LOOP.md).

  scaffold(p, reg)           copy templates/unity into the project root, add the Godot mirror + shared/ junctions
  headless(p, reg, method)   run the editor in batchmode on the project, tail the log, return its exit code
  build(p, reg, platform)    Builder.Android / Builder.Windows headless; returns Builds/last_build.json
  deploy(p, reg)             build + adb install + launch + logcat tab
  adb(reg)                   adb.exe from PATH or the Android module of the installed editor

Everything blocks and prints; `wb unity <project> ...` is the CLI, `wb open <project> setup|build|deploy`
opens a terminal tab running it so the window never freezes.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .registry import Project, Registry
from . import launch as L

TEMPLATES = L.WORKBENCH_ROOT / "templates"
PLATFORMS = {
    "android": ("Android", "Workbench.Builder.Android"),
    "windows": ("Win64", "Workbench.Builder.Windows"),
}


class UnityError(L.LaunchError):
    pass


# ------------------------------------------------------------------ scaffold
def scaffold(p: Project, reg: Registry, run_setup: bool = True, log=print) -> int:
    """Create a Unity project at p.root from templates/unity, plus godot/ and shared/."""
    root = p.root
    root.mkdir(parents=True, exist_ok=True)
    if (root / "ProjectSettings" / "ProjectVersion.txt").exists():
        log(f"{root} is already a Unity project; adding template files that are missing")
    _copy_missing(TEMPLATES / "unity", root, log)
    version = p.extra.get("unity_version") or _newest_editor(reg)
    if not version:
        raise UnityError("no unity_version in the registry and no editor under apps.unity_editors")
    pv = root / "ProjectSettings" / "ProjectVersion.txt"
    if not pv.exists():
        pv.parent.mkdir(parents=True, exist_ok=True)
        pv.write_text(f"m_EditorVersion: {version}\n", encoding="utf-8")
        log(f"ProjectVersion.txt -> {version}")
    manifest = root / "Packages" / "manifest.json"
    if not manifest.exists():
        # built-in modules differ per editor (6.x dropped com.unity.modules.vr), so list what this one ships
        mods = builtin_modules(reg, version)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"dependencies": {m: "1.0.0" for m in mods}}, indent=2) + "\n", encoding="utf-8")
        log(f"Packages/manifest.json: {len(mods)} built-in modules of Unity {version}; Setup.cs adds the rest")
    readme = root / "README.md"
    if readme.exists() and "<project>" in readme.read_text(encoding="utf-8"):
        readme.write_text(readme.read_text(encoding="utf-8").replace("<project>", p.name), encoding="utf-8")

    # Godot mirror
    gdir = p.godot_dir or root / "godot"
    if not (gdir / "project.godot").exists():
        gdir.mkdir(parents=True, exist_ok=True)
        gv = godot_version(reg) or "4.4"
        for f in (TEMPLATES / "godot").iterdir():
            if f.is_file():
                body = f.read_text(encoding="utf-8").replace("{name}", p.name).replace("{godot_version}", gv)
                (gdir / f.name).write_text(body, encoding="utf-8")
        log(f"godot mirror at {gdir} (features {gv})")

    # shared/ + junctions
    shared = root / "shared"
    shared.mkdir(exist_ok=True)
    if not (shared / "README.md").exists():
        (shared / "README.md").write_text(
            "Exchange folder: glTF / textures / audio edited once, seen by Unity (Assets/Shared) and Godot (godot/shared).\n"
            "Unity writes .meta sidecars here and Godot writes .import ones; each engine ignores the other's.\n",
            encoding="utf-8")
    junction(root / "Assets" / "Shared", shared, log)
    junction(gdir / "shared", shared, log)

    # git
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=root, check=False)
        subprocess.run(["git", "lfs", "install", "--local"], cwd=root, check=False, capture_output=True)
        merge = L.unity_exe(reg, version).parent / "Data" / "Tools" / "UnityYAMLMerge.exe"
        if merge.exists():
            subprocess.run(["git", "config", "merge.unityyamlmerge.name", "Unity SmartMerge"], cwd=root)
            subprocess.run(["git", "config", "merge.unityyamlmerge.driver",
                            f'"{merge}" merge -p %O %A %B %A'], cwd=root)
            subprocess.run(["git", "config", "merge.unityyamlmerge.recursive", "binary"], cwd=root)
        log("git init + lfs + UnityYAMLMerge driver")

    if run_setup:
        log("running Workbench.Setup headless (first run imports packages: a few minutes) ...")
        return headless(p, reg, "Workbench.Setup.Headless", quit_flag=False, log=log)
    return 0


def _copy_missing(src: Path, dst: Path, log) -> None:
    n = 0
    for f in src.rglob("*"):
        if f.is_dir():
            continue
        rel = f.relative_to(src)
        target = dst / rel
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        n += 1
    log(f"template: {n} file(s) copied from {src}")


def junction(link: Path, target: Path, log=print) -> None:
    if link.exists() or link.is_symlink():
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)
    log(f"junction {link} -> {target}")


def builtin_modules(reg: Registry, version: str) -> list[str]:
    """com.unity.modules.* that ship with this editor (what a fresh project's manifest lists)."""
    d = L.unity_exe(reg, version).parent / "Data" / "Resources" / "PackageManager" / "BuiltInPackages"
    mods = sorted(x.name for x in d.iterdir() if x.is_dir() and x.name.startswith("com.unity.modules.")) if d.exists() else []
    return mods or ["com.unity.modules.ui", "com.unity.modules.xr", "com.unity.modules.androidjni",
                    "com.unity.modules.physics", "com.unity.modules.imgui", "com.unity.modules.uielements"]


def _newest_editor(reg: Registry) -> str | None:
    ed = Path(reg.apps.get("unity_editors", ""))
    if not ed.exists():
        return None
    vs = sorted(d.name for d in ed.iterdir() if (d / "Editor" / "Unity.exe").exists())
    return vs[-1] if vs else None


def godot_version(reg: Registry) -> str | None:
    """'4.7' from .../Godot_v4.7.1-stable_win64.exe (what config/features wants)."""
    m = re.search(r"v(\d+\.\d+)", Path(reg.apps.get("godot", "")).name)
    return m.group(1) if m else None


# ------------------------------------------------------------------ headless editor
def project_lock(p: Project) -> bool:
    return (p.root / "Temp" / "UnityLockfile").exists()


def headless(p: Project, reg: Registry, method: str, extra: list[str] | None = None,
             build_target: str | None = None, quit_flag: bool = True, log=print) -> int:
    """Run `Unity -batchmode -nographics -projectPath root -executeMethod method`, blocking.

    The full log goes to logs/unity-<project>.log; [Workbench] lines and compiler/package errors are
    echoed as they appear. Returns the exit code.
    """
    version = L.unity_project_version(p.root) or p.extra.get("unity_version")
    if not version:
        raise UnityError(f"{p.name}: no ProjectSettings/ProjectVersion.txt (run `wb new {p.name}`)")
    exe = L.unity_exe(reg, version)
    if not exe.exists():
        raise UnityError(f"Unity {version} not installed at {exe}")
    if project_lock(p):
        raise UnityError(f"{p.name} is open in the editor (Temp/UnityLockfile). Close it, or use the Workbench menu inside Unity.")
    L.LOG_DIR.mkdir(exist_ok=True)
    logfile = L.LOG_DIR / f"unity-{p.name}.log"
    argv = [str(exe), "-batchmode", "-nographics", "-projectPath", str(p.root),
            "-logFile", str(logfile), "-executeMethod", method]
    if build_target:
        argv += ["-buildTarget", build_target]
    if quit_flag:
        argv.append("-quit")
    argv += extra or []
    log(f"$ {subprocess.list2cmdline(argv)}")
    logfile.write_text("", encoding="utf-8")
    t0 = time.time()
    proc = subprocess.Popen(argv, cwd=str(p.root), stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pos = 0
    try:
        while True:
            pos = _echo_log(logfile, pos, log)
            rc = proc.poll()
            if rc is not None:
                _echo_log(logfile, pos, log)
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        proc.kill()
        raise
    dt = time.time() - t0
    log(f"unity exited {rc} after {dt:.0f}s; full log: {logfile}")
    if rc != 0:
        tail = logfile.read_text(encoding="utf-8", errors="ignore").splitlines()[-25:]
        log("--- log tail ---\n" + "\n".join(tail))
    return rc


INTERESTING = re.compile(r"\[Workbench\]|error CS\d+|\w+Exception:|Aborting batchmode|Failed to|not installed|No Android|"
                         r"No valid Unity license|Licensing.*(?:Error|failed)", re.I)
NOISE = re.compile(r"Stacktrace|\(Filename:|^\s*at |Access token is unavailable", re.I)


def _echo_log(logfile: Path, pos: int, log) -> int:
    try:
        with open(logfile, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(pos)
            chunk = f.read()
            pos = f.tell()
    except OSError:
        return pos
    for line in chunk.splitlines():
        if INTERESTING.search(line) and not NOISE.search(line):
            log("  " + line.strip()[:200])
    return pos


# ------------------------------------------------------------------ build / deploy
def last_build(p: Project) -> dict | None:
    f = p.root / "Builds" / "last_build.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def has_android_module(reg: Registry, version: str) -> bool:
    return (L.unity_exe(reg, version).parent / "Data" / "PlaybackEngines" / "AndroidPlayer").exists()


def build(p: Project, reg: Registry, platform: str = "android", release: bool = False, log=print) -> dict:
    if platform not in PLATFORMS:
        raise UnityError(f"platform must be one of {', '.join(PLATFORMS)}")
    target, method = PLATFORMS[platform]
    if release:
        method += "Release"
    version = L.unity_project_version(p.root) or p.extra.get("unity_version", "")
    if platform == "android" and not has_android_module(reg, version):
        raise UnityError(f"Unity {version} has no Android Build Support module. Unity Hub > Installs > {version} > "
                         "Add modules > Android Build Support (+ OpenJDK, SDK & NDK), then retry.")
    rc = headless(p, reg, method, build_target=target, log=log)
    info = last_build(p)
    if rc != 0 or not info or not info.get("ok"):
        raise UnityError(f"build failed (exit {rc}); see logs/unity-{p.name}.log")
    log(f"built {info['path']} ({info.get('seconds')}s)")
    return info


def adb(reg: Registry) -> str | None:
    w = shutil.which("adb")
    if w:
        return w
    ed = Path(reg.apps.get("unity_editors", ""))
    if ed.exists():
        for d in sorted(ed.iterdir(), reverse=True):
            cand = d / "Editor" / "Data" / "PlaybackEngines" / "AndroidPlayer" / "SDK" / "platform-tools" / "adb.exe"
            if cand.exists():
                return str(cand)
    cand = Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe"
    return str(cand) if cand.exists() else None


def deploy(p: Project, reg: Registry, skip_build: bool = False, log=print) -> int:
    """Android: build (unless skip_build) -> adb install -r -> launch -> logcat in a terminal tab."""
    a = adb(reg)
    if not a:
        raise UnityError("adb not found: install the Android module for Unity (it ships platform-tools) or add adb to PATH")
    devs = subprocess.run([a, "devices"], capture_output=True, text=True).stdout.splitlines()[1:]
    devs = [d.split()[0] for d in devs if d.strip() and "\tdevice" in d]
    if not devs:
        raise UnityError("no device in `adb devices` (USB debugging on? `adb tcpip 5555` + `adb connect <ip>` for wireless)")
    info = last_build(p) if skip_build else build(p, reg, "android", log=log)
    if not info or info.get("target") != "Android" or not Path(info["path"]).exists():
        raise UnityError("no Android build to deploy; run without --skip-build")
    apk, ident = info["path"], info["identifier"]
    log(f"adb install -r {apk} -> {devs[0]}")
    r = subprocess.run([a, "-s", devs[0], "install", "-r", apk], capture_output=True, text=True)
    if r.returncode != 0:
        raise UnityError("adb install failed:\n" + (r.stdout + r.stderr)[-800:])
    subprocess.run([a, "-s", devs[0], "logcat", "-c"], capture_output=True)
    activity = f"{ident}/com.unity3d.player.UnityPlayerActivity"
    r = subprocess.run([a, "-s", devs[0], "shell", "am", "start", "-n", activity], capture_output=True, text=True)
    log(f"launched {activity}: {(r.stdout + r.stderr).strip()[:200]}")
    L._in_terminal(f'& "{a}" -s {devs[0]} logcat -s Unity:V ActivityManager:I AndroidRuntime:E',
                   p.root, f"logcat:{p.name}")
    return 0
