"""The workbench catalog: what data every project has, and how to load it.

Works the same from marimo, Jupyter, a script, or Julia via PythonCall.

    from wb import catalog
    catalog.show()                                  # everything, as a table (marimo) or text
    catalog.show("fieldrec")                        # one project
    arts = catalog.artifacts("fieldrec", kind="mcap")
    sess = catalog.load(arts[-1])                   # newest session -> {topic: pyarrow.Table}
    catalog.snippet(arts[-1])                       # the code that does the line above

Artifacts come from [projects.<name>.artifacts] in workbench.toml:

    [projects.fieldrec.artifacts]
    sessions = { glob = "<data-root>/sessions/*/*.mcap", kind = "mcap" }

Loaders are registered per kind in LOADERS; add one with @loader("kind").
"""
from __future__ import annotations

import glob as _glob
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import registry as R

# ------------------------------------------------------------------ model
@dataclass(frozen=True)
class Artifact:
    project: str
    group: str          # the key under [projects.X.artifacts], e.g. "sessions"
    kind: str           # mcap | safetensors | torch | parquet | arrow | dir | file
    path: Path

    @property
    def name(self) -> str:
        return self.path.stem if self.path.is_file() else self.path.name

    @property
    def size(self) -> int | None:
        """Bytes for files; None for directories (walking a 30 GB run folder is not free: see du())."""
        return None if self.path.is_dir() else self.path.stat().st_size

    def du(self) -> int:
        """Total bytes under a directory artifact (walks the tree)."""
        return sum(f.stat().st_size for f in self.path.rglob("*") if f.is_file())

    @property
    def mtime(self) -> datetime:
        return datetime.fromtimestamp(self.path.stat().st_mtime)

    def load(self, **kw: Any) -> Any:
        return load(self, **kw)

    def snippet(self) -> str:
        return snippet(self)

    def __repr__(self) -> str:
        return f"Artifact({self.project}/{self.group}: {self.name} [{self.kind}])"


# ------------------------------------------------------------- discovery
def projects(reg: R.Registry | None = None) -> list[str]:
    """Names of every registered project."""
    return list((reg or R.load()).projects)


def artifacts(project: str | None = None, kind: str | None = None, group: str | None = None,
              reg: R.Registry | None = None) -> list[Artifact]:
    """All artifacts, oldest first, filtered by project / kind / group."""
    reg = reg or R.load()
    out: list[Artifact] = []
    names = [reg.project(project).name] if project else list(reg.projects)
    for pname in names:
        p = reg.projects[pname]
        for g, spec in (p.extra.get("artifacts") or {}).items():
            if group and g != group:
                continue
            k = spec.get("kind", "file")
            if kind and k != kind:
                continue
            pattern = p.expand(spec["glob"])
            for hit in sorted(_glob.glob(pattern, recursive=True)):
                hp = Path(hit)
                if spec.get("dirs") and not hp.is_dir():
                    continue
                if not spec.get("dirs") and not hp.is_file():
                    continue
                out.append(Artifact(pname, g, k, hp))
    out.sort(key=lambda a: a.path.stat().st_mtime)
    return out


def latest(project: str, kind: str | None = None, group: str | None = None) -> Artifact:
    """Newest artifact for a project (optionally of one kind / group)."""
    arts = artifacts(project, kind=kind, group=group)
    if not arts:
        raise LookupError(f"no artifacts for {project} kind={kind} group={group}")
    return arts[-1]


def find(name: str, project: str | None = None) -> Artifact:
    """Artifact whose file/dir name contains `name` (newest if several)."""
    hits = [a for a in artifacts(project) if name.lower() in a.path.name.lower()]
    if not hits:
        raise LookupError(f"no artifact matching {name!r}")
    return hits[-1]


def _rows(arts: list[Artifact]) -> list[dict]:
    return [{"project": a.project, "group": a.group, "kind": a.kind, "name": a.name,
             "modified": a.mtime.strftime("%Y-%m-%d %H:%M"),
             "MB": round(a.size / 1e6, 2) if a.size is not None else None,
             "path": str(a.path)} for a in arts]


def show(project: str | None = None, kind: str | None = None, newest_first: bool = True):
    """Table of artifacts. Returns a marimo table inside marimo, else prints and returns rows."""
    arts = artifacts(project, kind=kind)
    if newest_first:
        arts = arts[::-1]
    rows = _rows(arts)
    try:
        import marimo as mo
        if mo.running_in_notebook():
            return mo.vstack([
                mo.md(f"**{len(rows)} artifacts**" + (f" in `{project}`" if project else "")
                      + " · `catalog.load(catalog.latest('<project>'))` · `catalog.snippet(a)` for the code"),
                mo.ui.table(rows, selection=None, page_size=15),
            ])
    except ImportError:
        pass
    w = max((len(r["name"]) for r in rows), default=4)
    for r in rows:
        mb = f"{r['MB']:>8} MB" if r["MB"] is not None else "       (dir)"
        print(f"{r['project']:<14} {r['kind']:<11} {r['name']:<{w}}  {r['modified']}  {mb}")
    return rows


# ---------------------------------------------------------------- loaders
LOADERS: dict[str, Callable[..., Any]] = {}
SNIPPETS: dict[str, str] = {}


def loader(kind: str, snippet_template: str = ""):
    """Register a loader for an artifact kind. The template gets {path} / {project} / {name}."""
    def deco(fn):
        LOADERS[kind] = fn
        if snippet_template:
            SNIPPETS[kind] = snippet_template
        return fn
    return deco


def load(a: Artifact, **kw: Any) -> Any:
    """Load an artifact with the loader for its kind."""
    if a.kind not in LOADERS:
        raise LookupError(f"no loader for kind {a.kind!r}; have {sorted(LOADERS)}")
    return LOADERS[a.kind](a.path, **kw)


def load_path(path: str | Path, kind: str, **kw: Any) -> Any:
    """Load a file by path with the loader for `kind` (for artifacts whose name is not unique)."""
    if kind not in LOADERS:
        raise LookupError(f"no loader for kind {kind!r}; have {sorted(LOADERS)}")
    return LOADERS[kind](Path(path), **kw)


def snippet(a: Artifact) -> str:
    """Copy-pasteable code that loads this artifact. Falls back to the full path when the
    name is shared by several artifacts in the project (fieldrec's per-node gnss/can/video)."""
    tpl = SNIPPETS.get(a.kind, "from wb import catalog\nobj = catalog.find({name!r}, {project!r}).load()")
    code = tpl.format(path=a.path.as_posix(), project=a.project, name=a.name, group=a.group)
    same = [b for b in artifacts(a.project, kind=a.kind) if b.name == a.name]
    if len(same) > 1:
        finder = f"catalog.find({a.name!r}, {a.project!r})"
        code = code.replace(f"catalog.load({finder})", f"catalog.load_path(path, {a.kind!r})")
        code = code.replace(finder, f"catalog.Artifact({a.project!r}, {a.group!r}, {a.kind!r}, __import__('pathlib').Path(path))")
        code = f"path = {a.path.as_posix()!r}   # {a.name!r} is not unique in {a.project}; this is the exact file\n" + code
    return code


@loader("mcap", '''from wb import catalog
sess = catalog.load(catalog.find({name!r}, {project!r}))   # {{topic: pyarrow.Table}}
list(sess)                                                   # topics
sess[list(sess)[0]].to_pandas().head()''')
def load_mcap(path: Path, topics: list[str] | None = None, limit: int | None = None) -> dict[str, Any]:
    """fieldrec MCAP -> {topic: pyarrow.Table}. JSON-encoded messages are flattened into columns,
    always with `log_time_ns`; other encodings land as a `data` binary column."""
    import pyarrow as pa
    from mcap.reader import make_reader

    rows: dict[str, list[dict]] = {}
    with open(path, "rb") as f:
        it = make_reader(f).iter_messages(topics=topics)
        try:
            for schema, channel, msg in it:
                row: dict[str, Any] = {"log_time_ns": msg.log_time}
                if channel.message_encoding == "json":
                    try:
                        row.update(json.loads(msg.data))
                    except (ValueError, TypeError):
                        row["data"] = msg.data
                else:
                    row["data"] = msg.data
                bucket = rows.setdefault(channel.topic, [])
                if limit is None or len(bucket) < limit:
                    bucket.append(row)
        except Exception:  # truncated tail (power cut) — keep what we have, like fieldrec does
            pass
    return {t: pa.Table.from_pylist(r) for t, r in rows.items()}


@loader("safetensors", '''from wb import catalog
tensors = catalog.load(catalog.find({name!r}, {project!r}))   # {{name: numpy array}}
{{k: v.shape for k, v in tensors.items()}}''')
def load_safetensors(path: Path, framework: str = "numpy") -> dict[str, Any]:
    """safetensors -> {name: array}. framework='numpy' (default) or 'torch'."""
    if framework == "torch":
        from safetensors.torch import load_file
    else:
        from safetensors.numpy import load_file
    return load_file(str(path))


@loader("torch", '''from wb import catalog
import torch
obj = torch.load({path!r}, map_location="cpu", weights_only=False)''')
def load_torch(path: Path, **kw: Any) -> Any:
    """torch.load on CPU. Full pickles (model objects) need weights_only=False and the defining code importable."""
    import torch
    kw.setdefault("map_location", "cpu")
    return torch.load(str(path), **kw)


@loader("parquet", '''from wb import catalog
tbl = catalog.load(catalog.find({name!r}, {project!r}))   # pyarrow.Table
tbl.to_pandas().head()''')
def load_parquet(path: Path, **kw: Any) -> Any:
    import pyarrow.parquet as pq
    return pq.read_table(str(path), **kw)


@loader("arrow", '''from wb import catalog
tbl = catalog.load(catalog.find({name!r}, {project!r}))   # pyarrow.Table''')
def load_arrow(path: Path, **kw: Any) -> Any:
    import pyarrow.feather as feather
    return feather.read_table(str(path), **kw)


@loader("json", '''from wb import catalog
obj = catalog.load(catalog.find({name!r}, {project!r}))''')
def load_json(path: Path, **kw: Any) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@loader("jsonl", '''from wb import catalog
rows = catalog.load(catalog.find({name!r}, {project!r}))   # list of dicts, one per line''')
def load_jsonl(path: Path, **kw: Any) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


@loader("csv", '''from wb import catalog
tbl = catalog.load(catalog.find({name!r}, {project!r}))   # pyarrow.Table
tbl.to_pandas().head()''')
def load_csv(path: Path, **kw: Any) -> Any:
    from pyarrow import csv as pacsv
    return pacsv.read_csv(str(path), **kw)


@loader("npz", '''from wb import catalog
arr = catalog.load(catalog.find({name!r}, {project!r}))   # ndarray (.npy) or NpzFile (.npz)''')
def load_npz(path: Path, **kw: Any) -> Any:
    import numpy as np
    return np.load(str(path), **kw)


@loader("text", '''from wb import catalog
text = catalog.load(catalog.find({name!r}, {project!r}))   # str
print(text[:2000])''')
def load_text(path: Path, **kw: Any) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


@loader("png", '''from wb import catalog
img = catalog.load(catalog.find({name!r}, {project!r}))   # PIL.Image if pillow is installed, else Path
img''')
def load_png(path: Path, **kw: Any) -> Any:
    try:
        from PIL import Image
        return Image.open(path)
    except ImportError:
        return Path(path)


@loader("file", '''from wb import catalog
p = catalog.find({name!r}, {project!r}).path   # pathlib.Path; open it with whatever reads this format''')
def load_file(path: Path, **kw: Any) -> Path:
    """Unknown format: hands back the Path."""
    return Path(path)


@loader("dir", '''from wb import catalog
d = catalog.find({name!r}, {project!r}).path   # pathlib.Path to the run folder
sorted(p.name for p in d.iterdir())''')
def load_dir(path: Path, **kw: Any) -> Path:
    """A run / session folder: returns the Path; look inside yourself."""
    return Path(path)


__all__ = ["Artifact", "projects", "artifacts", "latest", "find", "show", "load", "load_path", "snippet", "loader", "LOADERS"]
