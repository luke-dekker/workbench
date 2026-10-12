"""Shared fixtures: a synthetic registry in a temp dir, with one tiny generated file per loader kind.

Nothing here touches the real workbench.toml or spawns a process. `WORKBENCH_TOML` is pointed at
the generated registry for the duration of each test, so `catalog.*` and `wb.cli.main` see it.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from wb import launch as L
from wb import registry as R

# ------------------------------------------------------------ file makers
def write_parquet(path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    pq.write_table(pa.table({"x": [1, 2, 3], "y": ["a", "b", "c"]}), str(path))


def write_arrow(path: Path) -> None:
    import pyarrow as pa
    import pyarrow.feather as feather
    feather.write_feather(pa.table({"x": [1, 2, 3]}), str(path))


def write_safetensors(path: Path) -> None:
    import numpy as np
    from safetensors.numpy import save_file
    save_file({"w": np.zeros((2, 3), dtype=np.float32), "b": np.ones(3, dtype=np.float32)}, str(path))


def write_json(path: Path) -> None:
    path.write_text(json.dumps({"k": 1, "list": [1, 2]}), encoding="utf-8")


def write_jsonl(path: Path) -> None:
    path.write_text('{"i": 0}\n\n{"i": 1}\n{"i": 2}\n', encoding="utf-8")


def write_csv(path: Path) -> None:
    path.write_text("a,b\n1,x\n2,y\n", encoding="utf-8")


def write_npz(path: Path) -> None:
    import numpy as np
    np.savez(str(path), arr=np.arange(4))


def write_text(path: Path) -> None:
    path.write_text("hello workbench\n", encoding="utf-8")


def write_png(path: Path) -> None:
    # 1x1 PNG, hand-assembled so pillow is not needed to make it
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def write_mcap(path: Path) -> None:
    """Two JSON topics plus one raw-bytes topic, like a fieldrec session."""
    from mcap.writer import Writer

    with open(path, "wb") as f:
        w = Writer(f)
        w.start()
        schema = w.register_schema(name="json", encoding="jsonschema", data=b"{}")
        gnss = w.register_channel(topic="/gnss", message_encoding="json", schema_id=schema)
        imu = w.register_channel(topic="/imu", message_encoding="json", schema_id=schema)
        raw = w.register_channel(topic="/raw", message_encoding="cdr", schema_id=schema)
        for i in range(5):
            t = 1_000 + i
            w.add_message(gnss, log_time=t, publish_time=t, data=json.dumps({"lat": 0.0, "lon": 0.0, "i": i}).encode())
            w.add_message(imu, log_time=t, publish_time=t, data=json.dumps({"ax": float(i)}).encode())
        w.add_message(raw, log_time=2_000, publish_time=2_000, data=b"\x01\x02\x03")
        w.finish()


MAKERS = {
    "parquet": ("tables", ".parquet", write_parquet),
    "arrow": ("feathers", ".arrow", write_arrow),
    "safetensors": ("weights", ".safetensors", write_safetensors),
    "json": ("configs", ".json", write_json),
    "jsonl": ("streams", ".jsonl", write_jsonl),
    "csv": ("sheets", ".csv", write_csv),
    "npz": ("arrays", ".npz", write_npz),
    "text": ("notes", ".txt", write_text),
    "png": ("plots", ".png", write_png),
    "mcap": ("sessions", ".mcap", write_mcap),
    "file": ("blobs", ".glb", write_text),
}


# ------------------------------------------------------------- the fixture
@dataclass
class Fixture:
    """What `synthetic_registry` built."""
    toml: Path
    base: Path
    roots: dict[str, Path]
    files: dict[str, Path] = field(default_factory=dict)      # kind -> the single file for that kind (in `alpha`)
    run_dirs: list[Path] = field(default_factory=list)        # the `dir` artifacts (in `alpha/runs`)
    reg: R.Registry | None = None


def _toml_str(s: Path | str) -> str:
    return str(s).replace("\\", "/")


@pytest.fixture
def synthetic_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fixture:
    """Three projects:

    * ``alpha`` - python project with one artifact group per loader kind plus ``runs/*`` dirs
    * ``alpine`` - second project sharing the ``alp`` prefix (so prefix matching is ambiguous)
    * ``beta`` - python project with a godot dir and a ``[commands]`` entry
    * ``ghost`` - registered but its root does not exist
    """
    base = tmp_path / "dev"
    roots = {n: base / n for n in ("alpha", "alpine", "beta")}
    for r in roots.values():
        r.mkdir(parents=True)
    fx = Fixture(toml=tmp_path / "workbench.toml", base=base, roots=roots)

    alpha = roots["alpha"]
    art_lines = []
    for kind, (group, ext, make) in MAKERS.items():
        d = alpha / group
        d.mkdir()
        f = d / f"{kind}_sample{ext}"
        make(f)
        fx.files[kind] = f
        art_lines.append(f'{group} = {{ glob = "{{root}}/{group}/*{ext}", kind = "{kind}" }}')
    # run folders: three dirs with staggered mtimes, plus a stray file the dirs=true glob must skip
    runs = alpha / "runs"
    runs.mkdir()
    now = time.time()
    for i, name in enumerate(("run_a", "run_b", "run_c")):
        d = runs / name
        d.mkdir()
        (d / "out.json").write_text("{}", encoding="utf-8")
        os.utime(d, (now - 300 + i * 100, now - 300 + i * 100))
        fx.run_dirs.append(d)
    (runs / "stray.txt").write_text("not a run", encoding="utf-8")
    art_lines.append('runs = { glob = "{root}/runs/*", kind = "dir", dirs = true }')
    # a second parquet with the same stem as the first, in another group: snippet() must disambiguate
    dup = alpha / "tables_more"
    dup.mkdir()
    write_parquet(dup / "parquet_sample.parquet")
    art_lines.append('tables_more = { glob = "{root}/tables_more/*.parquet", kind = "parquet" }')
    # a glob that matches nothing
    art_lines.append('empty = { glob = "{root}/nothing/*.bin", kind = "file" }')

    beta = roots["beta"]
    (beta / "godot").mkdir()
    (beta / "godot" / "project.godot").write_text("[application]\n", encoding="utf-8")

    toml = f"""
[apps]
godot = "{_toml_str(tmp_path / 'bin' / 'godot')}"
unity_hub = "{_toml_str(tmp_path / 'bin' / 'hub')}"
unity_editors = "{_toml_str(tmp_path / 'editors')}"
blender = "{_toml_str(tmp_path / 'bin' / 'blender')}"
octave = "auto"
julia_env = "@notebooks"

[defaults]
marimo_extras = ["marimo-studio"]
notebooks_dir = "{_toml_str(tmp_path / 'scratch')}"

[projects.alpha]
root = "{_toml_str(alpha)}"
kind = "python"
tags = ["ml", "test"]
tools = ["code", "term", "marimo"]
[projects.alpha.artifacts]
{chr(10).join(art_lines)}

[projects.alpine]
root = "{_toml_str(roots['alpine'])}"
tools = ["code"]

[projects.beta]
root = "{_toml_str(beta)}"
kind = "python"
tags = ["godot"]
tools = ["web", "code", "godot", "godot_run"]
godot_dir = "{{root}}/godot"
[projects.beta.commands]
web = "uv run python serve.py --root {{root}}"

[projects.ghost]
root = "{_toml_str(base / 'ghost')}"
kind = "unity"
tools = ["unity", "unity_hub"]
unity_version = "6000.0.0f1"
"""
    fx.toml.write_text(toml, encoding="utf-8")
    monkeypatch.setenv(R.REGISTRY_ENV, str(fx.toml))
    fx.reg = R.load(fx.toml)
    return fx


# ------------------------------------------------------------- no spawning
class FakeProc:
    """Stands in for subprocess.Popen: records argv, never starts anything."""
    calls: list[dict] = []

    def __init__(self, argv, **kw):
        self.argv = list(argv)
        self.args = self.argv  # subprocess.run reads .args for CompletedProcess
        self.kw = kw
        self.pid = 4242
        self._terminated = False
        FakeProc.calls.append({"argv": self.argv, **kw})

    def poll(self):
        return 1 if self._terminated else None

    def terminate(self):
        self._terminated = True

    # subprocess.run() drives Popen as a context manager and calls communicate()/wait():
    # stop_servers() takes that path on Windows (taskkill), so the stub must support it.
    returncode = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def communicate(self, input=None, timeout=None):
        return b"", b""

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self._terminated = True


@pytest.fixture
def no_spawn(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> type[FakeProc]:
    """Patch every process start in wb.launch; logs go to a temp dir; RUNNING starts empty."""
    FakeProc.calls = []
    monkeypatch.setattr(L.subprocess, "Popen", FakeProc)
    monkeypatch.setattr(L, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(L, "RUNNING", [])
    return FakeProc
