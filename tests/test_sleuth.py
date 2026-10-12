"""wb.sleuth: disk and code scans on a fake project tree, and the TOML suggestion they produce."""
from __future__ import annotations

from pathlib import Path

import pytest

from wb import sleuth as S


@pytest.fixture
def fake_tree(synthetic_registry):
    """A project that writes results/*.json from code, keeps three run folders, and has noise."""
    p = synthetic_registry.reg.projects["beta"]
    root = p.root
    (root / "results").mkdir()
    for i in range(4):
        (root / "results" / f"case{i}_results.json").write_text('{"ok": true}', encoding="utf-8")
    (root / "results" / "plot.png").write_bytes(b"\x89PNG")
    (root / "runs").mkdir()
    for name in ("r1", "r2", "r3"):
        (root / "runs" / name).mkdir()
        (root / "runs" / name / "log.txt").write_text("x", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "in.csv").write_text("a\n1\n", encoding="utf-8")
    # a lone source-ish file at the root must not become an artifact group
    (root / "notes.md").write_text("# notes\n", encoding="utf-8")
    (root / "package.json").write_text("{}", encoding="utf-8")
    # noise dirs that the walk must skip
    for skip in (".venv", "node_modules", ".git"):
        (root / skip).mkdir()
        (root / skip / "junk.csv").write_text("x\n", encoding="utf-8")
    (root / "sim.py").write_text(
        "import json\n"
        "# json.dump(skipped, f)  comment lines are ignored\n"
        "out_dir = Path('results')\n"
        "parser.add_argument('--out', default='results')\n"
        "def run():\n"
        "    df.to_csv(out / 'x.csv')\n"
        "    json.dump(res, open(p, 'w'))\n"
        "    plt.savefig(out / 'plot.png')\n"
        "    np.save(out / 'a.npy', a)\n",
        encoding="utf-8")
    return p


def test_walk_skips_noise(fake_tree):
    names = {f.name for f in S._walk(fake_tree.root)}
    assert "junk.csv" not in names
    assert "sim.py" in names and "case0_results.json" in names


def test_scan_disk_groups_by_dir_and_ext(fake_tree):
    groups = {(g.directory.relative_to(fake_tree.root).as_posix(), g.ext): g for g in S.scan_disk(fake_tree.root)}
    assert groups[("results", ".json")].count == 4
    assert groups[("results", ".json")].kind == "json"
    assert groups[("results", ".png")].kind == "png"
    assert groups[("data", ".csv")].count == 1
    assert (".", ".md") in groups                                      # listed, filtered later
    assert (".", ".json") not in groups                                # package.json is config
    assert groups[("results", ".json")].bytes == 4 * len('{"ok": true}')
    assert groups[("results", ".json")].newest > 0


def test_scan_code_hits_and_hints(fake_tree):
    hits, hints = S.scan_code(fake_tree.root)
    kinds = [h.kind for h in hits]
    assert kinds == ["csv", "json", "png", "npz"]                     # one hit per line, first pattern wins
    assert all(h.file.name == "sim.py" for h in hits)
    assert hits[0].line == 6
    hint_text = [h.text for h in hints]
    assert any("out_dir" in t for t in hint_text)
    assert any("--out" in t for t in hint_text)
    assert not any("skipped" in h.text for h in hits)


def test_suggestion(fake_tree, synthetic_registry):
    rep = S.sleuth(fake_tree, synthetic_registry.reg, sibling_roots=[])
    sug = rep.suggestion()
    lines = sug.splitlines()
    assert lines[0] == "[projects.beta.artifacts]"
    assert any(l.startswith("results_json") and 'glob = "{root}/results/*.json"' in l and 'kind = "json"' in l for l in lines)
    assert any(l.startswith("results_png") for l in lines)
    assert any(l.startswith("data_csv") for l in lines)
    assert any(l.startswith("runs ") and 'kind = "dir", dirs = true' in l and "3 folders" in l for l in lines)
    assert not any("root_md" in l for l in lines)                      # one .md at the root is not an output
    assert "# 4 files" in sug


def test_suggestion_empty_root(synthetic_registry):
    p = synthetic_registry.reg.projects["alpine"]
    rep = S.sleuth(p, synthetic_registry.reg)
    assert rep.disk == [] and rep.code == []
    assert "nothing output-like found" in rep.suggestion()


def test_sleuth_missing_root(synthetic_registry):
    p = synthetic_registry.reg.projects["ghost"]
    rep = S.sleuth(p, synthetic_registry.reg)
    assert rep.disk == [] and rep.code == [] and rep.hints == []
    assert "root does not exist" in S.format_report(rep)


def test_format_report(fake_tree, synthetic_registry):
    rep = S.sleuth(fake_tree, synthetic_registry.reg)
    text = S.format_report(rep, max_code=2)
    assert text.startswith("# sleuth: beta")
    assert "## on disk" in text and "## code that writes files" in text
    assert "sim.py:6  [csv]" in text
    assert "... 2 more in 1 files" in text
    assert "## output-path config / CLI args" in text
    assert "## suggested registry lines" in text
    assert "[projects.beta.artifacts]" in text


def test_helpers(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "out" / "sub").mkdir(parents=True)
    assert S._rel(root, root) == "{root}"
    assert S._rel(root / "out" / "sub", root) == "{root}/out/sub"
    assert S._rel(tmp_path / "elsewhere", root) == (tmp_path / "elsewhere").as_posix()
    assert S._groupname("{root}/out/Sub-Dir", ".json") == "sub_dir_json"
    assert S._groupname("{root}", ".csv") == "root_csv"
    assert S._groupname("{root}/runs", "") == "runs"
    assert S._outputish(root / "out" / "sub", root)
    assert S._outputish(root / "checkpoints", root)
    assert not S._outputish(root / "src", root)
    assert not S._outputish(root, root)
    assert S.DiskGroup(root, ".parquet", 1, 1, 1.0).kind == "parquet"
    assert S.DiskGroup(root, ".weird", 1, 1, 1.0).kind == "file"


def test_run_dirs(tmp_path: Path):
    root = tmp_path / "p"
    (root / "runs" / "a").mkdir(parents=True)
    (root / "runs" / "b").mkdir()
    (root / "models" / "only").mkdir(parents=True)                     # one child: not run-style
    (root / "src" / "x").mkdir(parents=True)
    (root / "src" / "y").mkdir()
    assert S._run_dirs(root) == [root / "runs"]
