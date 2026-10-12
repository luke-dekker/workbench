"""wb.catalog.save: path choice from the group glob, one writer per kind, round trip through load."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from wb import catalog as C


# ------------------------------------------------------------- save_path
def test_save_path_from_glob(synthetic_registry):
    root = synthetic_registry.roots["alpha"]
    path, kind = C.save_path("alpha", "tables", "result")
    assert path == root / "tables" / "result.parquet" and kind == "parquet"


def test_save_path_default_name_is_timestamp(synthetic_registry):
    path, _ = C.save_path("alpha", "configs")
    assert path.parent == synthetic_registry.roots["alpha"] / "configs"
    assert path.suffix == ".json"
    assert len(path.stem) == len("20240101-120000") and path.stem[8] == "-"


def test_save_path_strips_repeated_suffix(synthetic_registry):
    path, _ = C.save_path("alpha", "tables", "result.parquet")
    assert path.name == "result.parquet"


def test_save_path_project_prefix(synthetic_registry):
    with pytest.raises(LookupError, match="in beta"):      # "be" resolves to beta, which has no groups
        C.save_path("be", "tables")
    with pytest.raises(KeyError):                           # "alp" is ambiguous
        C.save_path("alp", "tables")


def test_save_path_unknown_group(synthetic_registry):
    with pytest.raises(LookupError, match="no artifact group 'nope' in alpha"):
        C.save_path("alpha", "nope")
    with pytest.raises(LookupError, match="have none"):
        C.save_path("beta", "tables")


def test_save_path_rejects_dir_groups(synthetic_registry):
    with pytest.raises(ValueError, match="directory group"):
        C.save_path("alpha", "runs", "run_d")


def test_save_path_rejects_ambiguous_globs(synthetic_registry, tmp_path, monkeypatch):
    """Wildcards in a directory segment, or two in the file name, give no single path."""
    import tomllib
    from wb import registry as R
    text = synthetic_registry.toml.read_text(encoding="utf-8")
    text = text.replace(
        'empty = { glob = "{root}/nothing/*.bin", kind = "file" }',
        'empty = { glob = "{root}/nothing/*.bin", kind = "file" }\n'
        'nested = { glob = "{root}/sessions/*/*.mcap", kind = "mcap" }\n'
        'twostar = { glob = "{root}/x/*_*.json", kind = "json" }\n'
        'fixed = { glob = "{root}/x/only.json", kind = "json" }',
    )
    synthetic_registry.toml.write_text(text, encoding="utf-8")
    for group in ("nested", "twostar", "fixed"):
        with pytest.raises(ValueError, match="cannot choose a path"):
            C.save_path("alpha", group, "a")


def test_save_path_rejects_bad_names(synthetic_registry):
    for bad in ("a/b", "a\\b", ".parquet"):
        with pytest.raises(ValueError, match="bad artifact name"):
            C.save_path("alpha", "tables", bad)


# ------------------------------------------------------------------ save
def test_save_parquet_round_trip(synthetic_registry):
    import pyarrow as pa
    tbl = pa.table({"x": [1, 2], "y": ["a", "b"]})
    a = C.save(tbl, "alpha", "tables", "result")
    assert isinstance(a, C.Artifact)
    assert (a.project, a.group, a.kind) == ("alpha", "tables", "parquet")
    assert a.path == synthetic_registry.roots["alpha"] / "tables" / "result.parquet"
    assert a.load().equals(tbl)
    # the catalog sees it: newest in the group, found by name
    assert C.latest("alpha", group="tables").path == a.path
    assert C.find("result", "alpha").path == a.path


def test_save_table_from_dict_and_rows(synthetic_registry):
    a = C.save({"x": np.arange(3), "y": ["a", "b", "c"]}, "alpha", "tables", "cols")
    t = a.load()
    assert t.column_names == ["x", "y"] and t.column("x").to_pylist() == [0, 1, 2]
    b = C.save([{"x": 1}, {"x": 2}], "alpha", "feathers", "rows")
    assert b.kind == "arrow" and b.load().column("x").to_pylist() == [1, 2]
    c = C.save({"a": [1, 2], "b": ["x", "y"]}, "alpha", "sheets", "cells")
    assert c.kind == "csv" and c.load().column("b").to_pylist() == ["x", "y"]


def test_save_table_rejects_non_tables(synthetic_registry):
    with pytest.raises(TypeError, match="cannot make a table"):
        C.save(42, "alpha", "tables", "nope")
    assert not (synthetic_registry.roots["alpha"] / "tables" / "nope.parquet").exists()


def test_save_safetensors(synthetic_registry):
    arrays = {"w": np.ones((2, 2), dtype=np.float32), "b": [1.0, 2.0]}
    a = C.save(arrays, "alpha", "weights", "ckpt")
    got = a.load()
    assert set(got) == {"w", "b"}
    assert got["w"].shape == (2, 2) and list(got["b"]) == [1.0, 2.0]
    with pytest.raises(TypeError, match="dict of arrays"):
        C.save(np.ones(2), "alpha", "weights", "bad")


def test_save_npz(synthetic_registry):
    a = C.save({"arr": np.arange(4), "two": [[1, 2]]}, "alpha", "arrays", "pack")
    z = a.load()
    assert list(z["arr"]) == [0, 1, 2, 3] and z["two"].shape == (1, 2)


def test_save_json_with_numpy_values(synthetic_registry):
    obj = {"k": np.int64(3), "arr": np.arange(2), "p": Path("x") / "y"}
    a = C.save(obj, "alpha", "configs", "meta")
    assert a.kind == "json"
    assert a.load() == {"k": 3, "arr": [0, 1], "p": str(Path("x") / "y")}
    with pytest.raises(TypeError, match="not JSON serializable"):
        C.save({"o": object()}, "alpha", "configs", "bad")


def test_save_jsonl_and_text(synthetic_registry):
    a = C.save([{"i": 0}, {"i": 1}], "alpha", "streams", "log")
    assert a.load() == [{"i": 0}, {"i": 1}]
    assert a.path.read_text(encoding="utf-8").count("\n") == 2
    t = C.save("hello\n", "alpha", "notes", "readme")
    assert t.kind == "text" and t.load() == "hello\n"


def test_save_no_writer_for_kind(synthetic_registry):
    # `blobs` is kind "file": listed and loadable, but save has no format to write
    with pytest.raises(LookupError, match="no writer for kind 'file'"):
        C.save(b"...", "alpha", "blobs", "thing")


def test_save_refuses_to_overwrite_unless_asked(synthetic_registry):
    a = C.save({"v": 1}, "alpha", "configs", "same")
    with pytest.raises(FileExistsError, match="overwrite=True"):
        C.save({"v": 2}, "alpha", "configs", "same")
    assert a.load() == {"v": 1}
    b = C.save({"v": 2}, "alpha", "configs", "same", overwrite=True)
    assert b.path == a.path and b.load() == {"v": 2}


def test_save_creates_missing_directory(synthetic_registry, tmp_path):
    text = synthetic_registry.toml.read_text(encoding="utf-8")
    text = text.replace(
        'empty = { glob = "{root}/nothing/*.bin", kind = "file" }',
        'empty = { glob = "{root}/nothing/*.bin", kind = "file" }\n'
        'fresh = { glob = "{root}/out/deep/*.json", kind = "json" }',
    )
    synthetic_registry.toml.write_text(text, encoding="utf-8")
    a = C.save([1, 2], "alpha", "fresh", "first")
    assert a.path == synthetic_registry.roots["alpha"] / "out" / "deep" / "first.json"
    assert C.artifacts("alpha", group="fresh") == [a]


def test_save_default_name_then_latest(synthetic_registry):
    a = C.save({"v": 1}, "alpha", "configs")
    assert a.name != "json_sample"
    assert C.latest("alpha", group="configs").path == a.path


def test_save_with_explicit_registry(synthetic_registry, monkeypatch):
    from wb import registry as R
    monkeypatch.delenv(R.REGISTRY_ENV)
    monkeypatch.setattr(R, "DEFAULT_REGISTRY", synthetic_registry.base / "missing.toml")
    a = C.save({"v": 1}, "alpha", "configs", "explicit", reg=synthetic_registry.reg)
    assert a.load() == {"v": 1}


def test_writer_registration(synthetic_registry, monkeypatch):
    monkeypatch.setattr(C, "WRITERS", dict(C.WRITERS))

    @C.writer("file")
    def write_bytes(obj, path: Path):
        path.write_bytes(obj)

    assert C.WRITERS["file"] is write_bytes
    a = C.save(b"\x00\x01", "alpha", "blobs", "raw")
    assert a.path.suffix == ".glb" and a.path.read_bytes() == b"\x00\x01"


def test_every_writer_kind_has_a_loader():
    assert set(C.WRITERS) <= set(C.LOADERS)
