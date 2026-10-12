"""wb.catalog: discovery over the synthetic registry, every loader, snippets."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from wb import catalog as C

KINDS_WITH_LOADER = ["parquet", "arrow", "safetensors", "json", "jsonl", "csv", "npz", "text", "png", "mcap", "file"]


# -------------------------------------------------------------- discovery
def test_projects(synthetic_registry):
    assert C.projects() == ["alpha", "alpine", "beta", "ghost"]
    assert C.projects(synthetic_registry.reg) == C.projects()


def test_artifacts_everything(synthetic_registry):
    arts = C.artifacts()
    by_group = {}
    for a in arts:
        by_group.setdefault((a.project, a.group), []).append(a)
    # one file per kind group, the duplicate parquet, three run dirs, nothing for the dead glob
    assert len(by_group[("alpha", "tables")]) == 1
    assert len(by_group[("alpha", "tables_more")]) == 1
    assert len(by_group[("alpha", "runs")]) == 3
    assert ("alpha", "empty") not in by_group
    assert all(a.project == "alpha" for a in arts)          # the other projects declare nothing


def test_artifacts_filters(synthetic_registry):
    assert {a.kind for a in C.artifacts("alpha", kind="parquet")} == {"parquet"}
    assert len(C.artifacts("alpha", kind="parquet")) == 2
    assert [a.group for a in C.artifacts("alpha", group="sessions")] == ["sessions"]
    assert C.artifacts("alpha", kind="parquet", group="tables")[0].path == synthetic_registry.files["parquet"]
    assert C.artifacts("beta") == []
    assert C.artifacts("alpha", kind="nope") == []


def test_artifacts_accepts_prefix(synthetic_registry):
    assert C.artifacts("be") == []
    with pytest.raises(KeyError):
        C.artifacts("alp")


def test_artifacts_dirs_flag(synthetic_registry):
    runs = C.artifacts("alpha", group="runs")
    assert all(a.path.is_dir() for a in runs)
    assert {a.name for a in runs} == {"run_a", "run_b", "run_c"}     # stray.txt skipped
    files = C.artifacts("alpha", group="tables")
    assert all(a.path.is_file() for a in files)


def test_artifacts_sorted_oldest_first(synthetic_registry):
    runs = C.artifacts("alpha", group="runs")
    assert [a.name for a in runs] == ["run_a", "run_b", "run_c"]
    mtimes = [a.path.stat().st_mtime for a in runs]
    assert mtimes == sorted(mtimes)


def test_latest(synthetic_registry):
    assert C.latest("alpha", group="runs").name == "run_c"
    # bump run_a so it becomes the newest
    t = time.time() + 60
    os.utime(synthetic_registry.run_dirs[0], (t, t))
    assert C.latest("alpha", group="runs").name == "run_a"
    assert C.latest("alpha", kind="mcap").kind == "mcap"


def test_latest_raises_when_empty(synthetic_registry):
    with pytest.raises(LookupError, match="no artifacts for beta"):
        C.latest("beta")
    with pytest.raises(LookupError):
        C.latest("alpha", group="empty")


def test_find(synthetic_registry):
    a = C.find("MCAP_sample")                         # case-insensitive substring
    assert a.kind == "mcap" and a.project == "alpha"
    assert C.find("run_b", "alpha").path == synthetic_registry.run_dirs[1]
    with pytest.raises(LookupError):
        C.find("does-not-exist")


def test_artifact_properties(synthetic_registry):
    f = C.artifacts("alpha", group="tables")[0]
    assert f.name == "parquet_sample"                 # stem for files
    assert f.size == synthetic_registry.files["parquet"].stat().st_size
    assert f.mtime.year >= 2020
    assert repr(f) == "Artifact(alpha/tables: parquet_sample [parquet])"
    d = C.artifacts("alpha", group="runs")[0]
    assert d.name == "run_a"                          # full name for dirs
    assert d.size is None
    assert d.du() == (d.path / "out.json").stat().st_size


def test_show_prints_rows(synthetic_registry, capsys):
    rows = C.show("alpha", kind="parquet")
    out = capsys.readouterr().out
    assert len(rows) == 2
    assert rows[0].keys() == {"project", "group", "kind", "name", "modified", "MB", "path"}
    assert "parquet_sample" in out and "MB" in out
    newest_first = [r["path"] for r in rows]
    oldest_first = [str(a.path) for a in C.artifacts("alpha", kind="parquet")]
    assert newest_first == oldest_first[::-1]
    assert C.show("alpha", kind="parquet", newest_first=False)[0]["path"] == oldest_first[0]


def test_show_dirs_have_no_mb(synthetic_registry, capsys):
    rows = C.show("alpha", kind="dir")
    assert all(r["MB"] is None for r in rows)
    assert "(dir)" in capsys.readouterr().out


# ---------------------------------------------------------------- loaders
def test_every_kind_in_fixture_has_a_loader(synthetic_registry):
    for kind in KINDS_WITH_LOADER:
        assert kind in C.LOADERS
    assert "dir" in C.LOADERS and "torch" in C.LOADERS


def _one(kind: str) -> C.Artifact:
    arts = [a for a in C.artifacts("alpha", kind=kind) if a.group != "tables_more"]
    assert len(arts) == 1, kind
    return arts[0]


def test_load_parquet(synthetic_registry):
    t = C.load(_one("parquet"))
    assert t.column_names == ["x", "y"] and t.num_rows == 3


def test_load_arrow(synthetic_registry):
    assert C.load(_one("arrow")).column("x").to_pylist() == [1, 2, 3]


def test_load_safetensors(synthetic_registry):
    import numpy as np
    w = C.load(_one("safetensors"))
    assert set(w) == {"w", "b"}
    assert w["w"].shape == (2, 3) and isinstance(w["w"], np.ndarray)


def test_load_json(synthetic_registry):
    assert C.load(_one("json")) == {"k": 1, "list": [1, 2]}


def test_load_jsonl_skips_blank_lines(synthetic_registry):
    assert C.load(_one("jsonl")) == [{"i": 0}, {"i": 1}, {"i": 2}]


def test_load_csv(synthetic_registry):
    t = C.load(_one("csv"))
    assert t.column_names == ["a", "b"] and t.num_rows == 2


def test_load_npz(synthetic_registry):
    z = C.load(_one("npz"))
    assert list(z["arr"]) == [0, 1, 2, 3]


def test_load_text(synthetic_registry):
    assert C.load(_one("text")) == "hello workbench\n"


def test_load_png(synthetic_registry):
    img = C.load(_one("png"))
    try:
        from PIL import Image
        assert isinstance(img, Image.Image) and img.size == (1, 1)
    except ImportError:
        assert img == _one("png").path


def test_load_file_and_dir_return_paths(synthetic_registry):
    f = _one("file")
    assert C.load(f) == f.path
    d = C.artifacts("alpha", group="runs")[0]
    assert C.load(d) == d.path and d.load().is_dir()


def test_load_mcap(synthetic_registry):
    sess = C.load(_one("mcap"))
    assert set(sess) == {"/gnss", "/imu", "/raw"}
    gnss = sess["/gnss"]
    assert gnss.num_rows == 5
    assert {"log_time_ns", "lat", "lon", "i"} <= set(gnss.column_names)
    assert gnss.column("i").to_pylist() == [0, 1, 2, 3, 4]
    assert sess["/raw"].column("data").to_pylist() == [b"\x01\x02\x03"]


def test_load_mcap_topics_and_limit(synthetic_registry):
    sess = C.load(_one("mcap"), topics=["/imu"], limit=2)
    assert list(sess) == ["/imu"]
    assert sess["/imu"].num_rows == 2


def test_load_mcap_truncated_tail(synthetic_registry, tmp_path):
    src = synthetic_registry.files["mcap"].read_bytes()
    cut = tmp_path / "cut.mcap"
    cut.write_bytes(src[: len(src) * 2 // 3])
    sess = C.load_path(cut, "mcap")                   # keeps what it could read, no raise
    assert isinstance(sess, dict)


def test_load_unknown_kind(synthetic_registry):
    a = C.Artifact("alpha", "g", "mystery", synthetic_registry.files["json"])
    with pytest.raises(LookupError, match="no loader for kind 'mystery'"):
        C.load(a)
    with pytest.raises(LookupError):
        C.load_path(synthetic_registry.files["json"], "mystery")


def test_load_path(synthetic_registry):
    assert C.load_path(str(synthetic_registry.files["json"]), "json") == {"k": 1, "list": [1, 2]}


def test_artifact_load_method(synthetic_registry):
    a = _one("json")
    assert a.load() == C.load(a)


def test_loader_registration(synthetic_registry, monkeypatch):
    monkeypatch.setattr(C, "LOADERS", dict(C.LOADERS))
    monkeypatch.setattr(C, "SNIPPETS", dict(C.SNIPPETS))

    @C.loader("upper", "from wb import catalog\nobj = catalog.load(catalog.find({name!r}, {project!r}))")
    def load_upper(path: Path, **kw):
        return path.read_text().upper()

    assert C.LOADERS["upper"] is load_upper
    assert "upper" in C.SNIPPETS
    assert C.load_path(synthetic_registry.files["text"], "upper") == "HELLO WORKBENCH\n"


# ---------------------------------------------------------------- snippets
def _exec_snippet(code: str) -> dict:
    """Run the snippet up to and including the line that assigns the loaded object.

    Later lines are display helpers (`.to_pandas().head()`, `img`) that need pandas or a notebook;
    the whole snippet still has to compile.
    """
    compile(code, "<snippet>", "exec")
    keep = []
    for ln in code.splitlines():
        keep.append(ln)
        if " = " in ln and "catalog." in ln and not ln.startswith("path ="):
            break
    ns: dict = {}
    exec("\n".join(keep), ns)
    return ns


@pytest.mark.parametrize("kind", [k for k in KINDS_WITH_LOADER if k != "parquet"])
def test_snippet_round_trip(synthetic_registry, kind):
    a = _one(kind)
    code = C.snippet(a)
    assert code.startswith("from wb import catalog")
    assert a.name in code and a.project in code
    ns = _exec_snippet(code)
    loaded = [v for k, v in ns.items() if not k.startswith("__") and k != "catalog"]
    assert len(loaded) == 1
    got = loaded[0]
    want = C.load(a)
    if kind in ("parquet", "arrow", "csv"):
        assert got.equals(want)
    elif kind == "mcap":
        assert set(got) == set(want)
    elif kind == "safetensors":
        assert set(got) == set(want)
    elif kind == "npz":
        assert list(got["arr"]) == list(want["arr"])
    else:
        assert got == want


def test_snippet_dir(synthetic_registry):
    a = C.artifacts("alpha", group="runs")[0]
    ns = _exec_snippet(C.snippet(a))
    assert ns["d"] == a.path


def test_snippet_duplicate_name_uses_exact_path(synthetic_registry):
    """`parquet_sample` exists in two groups, so the snippet must not rely on catalog.find."""
    tables, more = (C.artifacts("alpha", kind="parquet", group=g)[0] for g in ("tables", "tables_more"))
    assert tables.name == more.name
    for a in (tables, more):
        code = C.snippet(a)
        assert code.startswith(f"path = {a.path.as_posix()!r}")
        assert "catalog.find(" not in code
        assert "catalog.load_path(path, 'parquet')" in code
        ns = _exec_snippet(code)
        assert ns["path"] == a.path.as_posix()
        assert ns["tbl"].equals(C.load(a))


def test_snippet_method_and_fallback_template(synthetic_registry):
    a = _one("json")
    assert a.snippet() == C.snippet(a)
    b = C.Artifact("alpha", "g", "mystery", synthetic_registry.files["json"])
    code = C.snippet(b)
    assert "catalog.find('json_sample', 'alpha').load()" in code
