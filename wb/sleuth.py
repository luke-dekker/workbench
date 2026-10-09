"""Sleuth: figure out where a project writes its outputs, and suggest [artifacts] lines.

    wb sleuth struct-sim            # report + suggested TOML
    wb sleuth struct-sim --apply    # append the suggestion to workbench.toml (commented, for review)

Two sources of evidence, combined:
  1. what is on disk: data-ish files under the root (and known sibling data dirs), grouped by
     directory + extension, skipping envs/caches/sources
  2. what the code says: write calls and output-path config in the project's source
     (to_csv, savefig, np.save, torch.save, json.dump, open(..., "w"), out_dir=..., --out ...)
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .registry import Project, Registry

SKIP = {".venv", "venv", "node_modules", ".git", "__pycache__", ".mypy_cache", ".pytest_cache",
        ".ruff_cache", "dist", "build", "site-packages", ".ipynb_checkpoints", "__marimo__"}
SKIP_SUFFIX = {".egg-info"}

# extension -> catalog kind
KINDS = {
    ".mcap": "mcap", ".safetensors": "safetensors", ".pt": "torch", ".pth": "torch", ".ckpt": "torch",
    ".parquet": "parquet", ".arrow": "arrow", ".feather": "arrow", ".csv": "csv", ".tsv": "csv",
    ".npz": "npz", ".npy": "npz", ".json": "json", ".jsonl": "json", ".h5": "file", ".hdf5": "file",
    ".png": "png", ".jpg": "png", ".jpeg": "png", ".svg": "png", ".pdf": "file", ".html": "file",
    ".mp4": "file", ".wav": "file", ".gltf": "file", ".glb": "file", ".obj": "file", ".ply": "file",
    ".stl": "file", ".step": "file", ".stp": "file", ".dxf": "file", ".las": "file", ".laz": "file",
    ".tif": "file", ".tiff": "file", ".log": "file", ".txt": "file", ".md": "file", ".toml": "file",
    ".yaml": "file", ".yml": "file", ".db": "file", ".sqlite": "file", ".pkl": "file", ".pickle": "file",
}
# extensions that are usually source/config, not outputs, unless they sit in an output-looking dir
SOURCEISH = {".json", ".toml", ".yaml", ".yml", ".md", ".txt", ".html", ".log"}
OUTPUT_DIR_WORDS = ("out", "output", "outputs", "result", "results", "run", "runs", "export", "exports",
                    "artifact", "artifacts", "report", "reports", "plot", "plots", "fig", "figs", "figures",
                    "render", "renders", "log", "logs", "cache", "checkpoint", "checkpoints", "model",
                    "models", "weights", "data", "sessions", "recordings", "captures", "scans", "sweep")

SRC_EXT = {".py", ".jl", ".m", ".gd", ".cs", ".js", ".ts", ".tsx", ".sh", ".ps1", ".toml", ".yaml", ".yml", ".cfg", ".ini"}
WRITE_PATTERNS = [
    (r"\.to_csv\(", "csv"), (r"\.to_parquet\(", "parquet"), (r"\.write_parquet\(", "parquet"),
    (r"\.to_json\(", "json"), (r"json\.dump\(", "json"), (r"np\.save[z]?(_compressed)?\(", "npz"),
    (r"torch\.save\(", "torch"), (r"save_file\(", "safetensors"), (r"savefig\(", "png"),
    (r"\.write_image\(", "png"), (r"\.write_html\(", "file"), (r"imwrite\(|imsave\(|\.save\(.*\.png", "png"),
    (r"McapLog\(|mcap\.writer|Writer\(", "mcap"), (r"open\([^)]*['\"][wa]b?['\"]", "file"),
    (r"\.write_text\(|\.write_bytes\(", "file"), (r"mkdir\(", "dir"),
    (r"export_|save_session|write_session", "file"),
]
PATH_HINTS = re.compile(
    r"""(?x)
    (?:out(?:put)?s?_?dir|out(?:put)?s?_?path|results?_?dir|run(?:s)?_?dir|export_?dir|save_?dir|log_?dir|
       artifacts?_?dir|report_?dir|cache_?dir|OUT|OUTPUT|RESULTS|RUNS)\s*[=:]\s*(?P<val>[^\n,)]+)
    |add_argument\(\s*["'](?P<arg>--?(?:out|output|outdir|out-dir|results|save|export)[\w-]*)["']
    |Path\(\s*["'](?P<lit>[^"']+)["']\s*\)\s*/\s*["'](?P<lit2>[^"']+)["']
    """)


@dataclass
class DiskGroup:
    directory: Path
    ext: str
    count: int
    bytes: int
    newest: float

    @property
    def kind(self) -> str:
        return KINDS.get(self.ext, "file")


@dataclass
class CodeHit:
    file: Path
    line: int
    text: str
    kind: str


@dataclass
class Report:
    project: str
    root: Path
    disk: list[DiskGroup] = field(default_factory=list)
    code: list[CodeHit] = field(default_factory=list)
    hints: list[CodeHit] = field(default_factory=list)
    siblings: list[Path] = field(default_factory=list)

    def suggestion(self) -> str:
        """TOML artifact lines. Only groups that look like outputs."""
        lines = [f"[projects.{self.project}.artifacts]"]
        seen = set()
        for g in sorted(self.disk, key=lambda g: (-g.count, g.ext)):
            if g.kind == "file" and g.ext in SOURCEISH and not _outputish(g.directory, self.root):
                continue
            if g.ext in SOURCEISH and g.kind in ("file",) and g.count < 3:
                continue
            rel = _rel(g.directory, self.root)
            name = _groupname(rel, g.ext)
            if name in seen:
                continue
            seen.add(name)
            pattern = f"{rel}/*{g.ext}" if rel else f"{{root}}/*{g.ext}"
            lines.append(f'{name:<14} = {{ glob = "{pattern}", kind = "{g.kind}" }}'
                         f'   # {g.count} files, {g.bytes / 1e6:.1f} MB')
        # run-style folders: an output-ish dir whose children are dirs
        for d in _run_dirs(self.root):
            rel = _rel(d, self.root)
            name = _groupname(rel, "")
            if name not in seen:
                seen.add(name)
                lines.append(f'{name:<14} = {{ glob = "{rel}/*", kind = "dir", dirs = true }}'
                             f'   # {sum(1 for _ in d.iterdir())} folders')
        if len(lines) == 1:
            lines.append("# (nothing output-like found on disk yet; see code hits above for where it will go)")
        return "\n".join(lines)


def _rel(d: Path, root: Path) -> str:
    try:
        r = d.relative_to(root).as_posix()
        return "{root}" + ("/" + r if r else "")
    except ValueError:
        return d.as_posix()


def _groupname(rel: str, ext: str) -> str:
    tail = rel.rstrip("/").split("/")[-1].replace("{root}", "root")
    base = re.sub(r"[^a-z0-9]+", "_", tail.lower()).strip("_") or "root"
    return f"{base}_{ext.lstrip('.')}" if ext else base


def _outputish(d: Path, root: Path) -> bool:
    parts = [p.lower() for p in d.relative_to(root).parts] if d != root and d.is_relative_to(root) else []
    return any(any(w == part or part.startswith(w) for w in OUTPUT_DIR_WORDS) for part in parts)


def _run_dirs(root: Path) -> list[Path]:
    out = []
    for d in root.iterdir():
        if d.is_dir() and d.name.lower() in OUTPUT_DIR_WORDS and d.name not in SKIP:
            kids = [k for k in d.iterdir() if k.is_dir()]
            if len(kids) >= 2:
                out.append(d)
    return out


def _walk(root: Path, max_depth: int = 4):
    def rec(d: Path, depth: int):
        try:
            for e in d.iterdir():
                if e.is_dir():
                    if e.name in SKIP or e.name.startswith(".") or any(e.name.endswith(s) for s in SKIP_SUFFIX):
                        continue
                    if depth < max_depth:
                        yield from rec(e, depth + 1)
                else:
                    yield e
        except OSError:
            return
    yield from rec(root, 0)


CONFIG_NAMES = {"package.json", "package-lock.json", "tsconfig.json", "tsconfig.node.json", "vite.config.json",
                "pyproject.toml", "uv.lock", "project.toml", "manifest.toml", "readme.md", "license.md",
                "changelog.md", "index.html", ".pre-commit-config.yaml"}


def scan_disk(root: Path) -> list[DiskGroup]:
    groups: dict[tuple[Path, str], list[Path]] = defaultdict(list)
    for f in _walk(root):
        ext = f.suffix.lower()
        if ext not in KINDS:
            continue
        if f.name.lower() in CONFIG_NAMES or f.name.lower().startswith("tsconfig"):
            continue
        groups[(f.parent, ext)].append(f)
    out = []
    for (d, ext), files in groups.items():
        stats = [f.stat() for f in files]
        out.append(DiskGroup(d, ext, len(files), sum(s.st_size for s in stats), max(s.st_mtime for s in stats)))
    return out


def scan_code(root: Path) -> tuple[list[CodeHit], list[CodeHit]]:
    hits, hints = [], []
    for f in _walk(root):
        if f.suffix.lower() not in SRC_EXT:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            for pat, kind in WRITE_PATTERNS:
                if re.search(pat, line):
                    hits.append(CodeHit(f, i, s[:110], kind))
                    break
            if PATH_HINTS.search(line):
                hints.append(CodeHit(f, i, s[:110], "path"))
    return hits, hints


def sleuth(p: Project, reg: Registry, sibling_roots: list[Path] | None = None) -> Report:
    rep = Report(p.name, p.root)
    if not p.root.exists():
        return rep
    rep.disk = scan_disk(p.root)
    rep.code, rep.hints = scan_code(p.root)
    # sibling data dirs that mention the project name (fieldrec -> field-data style)
    for base in (p.root.parent, Path.home(), Path.home() / "Documents"):
        try:
            for d in base.iterdir():
                if d.is_dir() and d != p.root and d.name.lower().replace("-", "").startswith(
                        p.name.lower().replace("-", "")[:5]) and d.name not in SKIP:
                    rep.siblings.append(d)
        except OSError:
            pass
    return rep


def format_report(rep: Report, max_code: int = 25) -> str:
    out = [f"# sleuth: {rep.project}  ({rep.root})", ""]
    if not rep.root.exists():
        return out[0] + "\n  root does not exist"
    out.append("## on disk (data-ish files, grouped by folder + extension)")
    for g in sorted(rep.disk, key=lambda g: (-g.bytes, g.ext))[:40]:
        out.append(f"  {g.count:>5} {g.ext:<12} {g.bytes / 1e6:>9.1f} MB  {_rel(g.directory, rep.root)}")
    if not rep.disk:
        out.append("  (none)")
    if rep.siblings:
        out.append("\n## sibling folders that look related (check these too)")
        out += [f"  {s}" for s in rep.siblings]
    out.append("\n## code that writes files")
    by_file = Counter(h.file for h in rep.code)
    for h in rep.code[:max_code]:
        out.append(f"  {h.file.relative_to(rep.root).as_posix()}:{h.line}  [{h.kind}]  {h.text}")
    if len(rep.code) > max_code:
        out.append(f"  ... {len(rep.code) - max_code} more in {len(by_file)} files")
    if rep.hints:
        out.append("\n## output-path config / CLI args")
        for h in rep.hints[:15]:
            out.append(f"  {h.file.relative_to(rep.root).as_posix()}:{h.line}  {h.text}")
    out.append("\n## suggested registry lines (review, then paste into workbench.toml)")
    out.append(rep.suggestion())
    return "\n".join(out)
