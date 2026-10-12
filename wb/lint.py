"""wb lint: check the registry against the machine it runs on.

    wb lint                 every project
    wb lint <project>       one project (prefix match)
    wb lint --strict        exit 1 on warnings too

Each finding is one line: ``LEVEL  project  message``. Exit code is 1 when there is at least
one error (or, with ``--strict``, any finding), 0 otherwise.

Errors (the registry is wrong):

* an ``[apps]`` path that does not exist (``auto`` and ``@env`` values are skipped)
* a tool in ``tools`` that is neither a built-in launcher nor a ``[commands]`` entry
* an artifact kind with no loader
* a ``godot_dir`` that does not exist or holds no ``project.godot``
* an ``[apps] unity_editors`` folder with no editor installed

Warnings (the registry may be right but nothing backs it up today):

* a project root that does not exist (``wb new <project>`` creates it)
* an artifact glob that matches nothing (skipped while the root is missing)
* a ``dirs = true`` group whose glob matches only files, and the reverse
* two artifact groups of a project matching a file with the same name
* a ``unity_version`` with no editor of that version under ``unity_editors``
* a ``defaults.notebooks_dir`` that does not exist
"""
from __future__ import annotations

import glob as _glob
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import registry as R

ERROR = "error"
WARN = "warning"


@dataclass(frozen=True)
class Finding:
    level: str          # ERROR | WARN
    project: str        # "" for registry-wide findings ([apps], [defaults])
    message: str

    def __str__(self) -> str:
        where = self.project or "-"
        return f"{self.level:<7} {where:<14} {self.message}"


# ------------------------------------------------------------- registry-wide
def lint_apps(reg: R.Registry) -> list[Finding]:
    out: list[Finding] = []
    for key, val in reg.apps.items():
        if not isinstance(val, str) or val in ("", "auto") or val.startswith("@"):
            continue
        path = Path(val)
        if not path.exists():
            out.append(Finding(ERROR, "", f"[apps] {key}: {val} does not exist"))
        elif key == "unity_editors" and not _unity_versions(reg):
            out.append(Finding(ERROR, "", f"[apps] unity_editors: no editor under {val}"))
    nb = reg.defaults.get("notebooks_dir")
    if nb and not Path(nb).exists():
        out.append(Finding(WARN, "", f"[defaults] notebooks_dir: {nb} does not exist"))
    return out


def _unity_versions(reg: R.Registry) -> list[str]:
    ed = Path(reg.apps.get("unity_editors", ""))
    if not ed.is_dir():
        return []
    return sorted(d.name for d in ed.iterdir() if (d / "Editor").is_dir())


# -------------------------------------------------------------- per project
def lint_project(p: R.Project, reg: R.Registry) -> list[Finding]:
    from . import catalog as C
    from . import launch as L

    out: list[Finding] = []
    f = lambda level, msg: out.append(Finding(level, p.name, msg))  # noqa: E731

    if not p.exists:
        f(WARN, f"root {p.root} does not exist (wb new {p.name} creates it)")

    for tool in p.tools:
        if tool not in L.BUILTIN and tool not in p.commands:
            f(ERROR, f"unknown tool {tool!r} (not a builtin, not in [commands])")
    for name in p.commands:
        if name not in p.tools:
            f(WARN, f"command {name!r} is not listed in tools")

    if p.exists:
        g = p.extra.get("godot_dir")
        if g:
            gdir = p.godot_dir
            if not gdir.is_dir():
                f(ERROR, f"godot_dir {gdir} does not exist")
            elif not (gdir / "project.godot").exists():
                f(ERROR, f"godot_dir {gdir} has no project.godot")

    uv = p.extra.get("unity_version")
    if uv and uv not in _unity_versions(reg):
        f(WARN, f"unity_version {uv} is not installed under [apps] unity_editors")

    # artifacts
    groups = p.extra.get("artifacts") or {}
    names: dict[str, list[str]] = defaultdict(list)       # artifact name -> groups it appears in
    for g, spec in groups.items():
        if not isinstance(spec, dict) or "glob" not in spec:
            f(ERROR, f"artifacts.{g}: needs a glob")
            continue
        kind = spec.get("kind", "file")
        if kind not in C.LOADERS:
            f(ERROR, f"artifacts.{g}: no loader for kind {kind!r} (have {', '.join(sorted(C.LOADERS))})")
        pattern = p.expand(spec["glob"])
        hits = [Path(h) for h in _glob.glob(pattern, recursive=True)]
        want_dirs = bool(spec.get("dirs"))
        kept = [h for h in hits if (h.is_dir() if want_dirs else h.is_file())]
        if not kept:
            if hits:
                have = "directories" if want_dirs else "files"
                need = "dirs = true" if not want_dirs else "dirs = false"
                f(WARN, f"artifacts.{g}: glob {pattern} matches no {have} (only the other kind; set {need}?)")
            elif p.exists or not spec["glob"].startswith("{root}"):
                f(WARN, f"artifacts.{g}: glob {pattern} matches nothing")
        for h in kept:
            names[h.stem if h.is_file() else h.name].append(g)
    for name, gs in sorted(names.items()):
        if len(gs) > 1:
            f(WARN, f"artifact name {name!r} appears in groups {', '.join(sorted(gs))}; pass group= to catalog.artifacts")
    return out


def lint(reg: R.Registry, project: str | None = None) -> list[Finding]:
    """Every finding for the registry, or for one project (prefix match) plus the [apps] checks."""
    out = lint_apps(reg)
    names = [reg.project(project).name] if project else list(reg.projects)
    for n in names:
        out.extend(lint_project(reg.projects[n], reg))
    return out


def errors(findings: list[Finding]) -> list[Finding]:
    return [x for x in findings if x.level == ERROR]


def summary(findings: list[Finding], n_projects: int) -> str:
    e = len(errors(findings))
    w = len(findings) - e
    if not findings:
        return f"ok: {n_projects} project(s), no findings"
    return f"{e} error(s), {w} warning(s) in {n_projects} project(s)"
