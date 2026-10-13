"""wb.lint: registry checks over the synthetic registry, and the `wb lint` command."""
from __future__ import annotations

from pathlib import Path

from wb import cli
from wb import lint as LINT
from wb import registry as R


def _msgs(findings, project=None, level=None):
    return [x.message for x in findings
            if (project is None or x.project == project) and (level is None or x.level == level)]


def test_clean_fixture_has_expected_findings_only(synthetic_registry):
    fx = synthetic_registry
    out = LINT.lint(fx.reg)
    # apps: the fixture's four app paths do not exist
    apps = _msgs(out, project="", level=LINT.ERROR)
    assert len(apps) == 4 and all("[apps]" in m for m in apps)
    assert any("notebooks_dir" in m for m in _msgs(out, project="", level=LINT.WARN))
    # alpha: the empty glob and the shared parquet stem
    alpha = _msgs(out, project="alpha")
    assert len(alpha) == 2
    assert any("artifacts.empty" in m and "matches nothing" in m for m in alpha)
    assert any("'parquet_sample'" in m and "tables, tables_more" in m for m in alpha)
    assert not _msgs(out, project="alpha", level=LINT.ERROR)
    # the same stem repeated within ONE group (per-session files) is not a clash
    assert not any("tables, tables," in m or m.endswith("groups tables, tables; pass group= to catalog.artifacts") for m in alpha)
    # beta: `web` is a command, godot_dir is fine
    assert _msgs(out, project="beta") == []
    # ghost: root missing, unity version not installed; its globs are not reported
    ghost = _msgs(out, project="ghost")
    assert len(ghost) == 2
    assert any("does not exist" in m and "wb new ghost" in m for m in ghost)
    assert any("unity_version 6000.0.0f1" in m for m in ghost)
    assert _msgs(out, project="alpine") == []


def test_unknown_tool_and_unlisted_command(synthetic_registry):
    fx = synthetic_registry
    p = fx.reg.projects["beta"]
    p.tools.append("frobnicate")
    p.commands["serve"] = "uv run serve"
    out = LINT.lint_project(p, fx.reg)
    assert _msgs(out, level=LINT.ERROR) == ["unknown tool 'frobnicate' (not a builtin, not in [commands])"]
    assert "command 'serve' is not listed in tools" in _msgs(out, level=LINT.WARN)


def test_godot_dir_checks(synthetic_registry):
    fx = synthetic_registry
    p = fx.reg.projects["beta"]
    (fx.roots["beta"] / "godot" / "project.godot").unlink()
    assert any("no project.godot" in m for m in _msgs(LINT.lint_project(p, fx.reg), level=LINT.ERROR))
    p.extra["godot_dir"] = "{root}/elsewhere"
    assert any("godot_dir" in m and "does not exist" in m
               for m in _msgs(LINT.lint_project(p, fx.reg), level=LINT.ERROR))


def test_unknown_kind_and_dirs_mismatch(synthetic_registry):
    fx = synthetic_registry
    p = fx.reg.projects["alpha"]
    arts = p.extra["artifacts"]
    arts["weird"] = {"glob": "{root}/configs/*.json", "kind": "hologram"}
    arts["runs_as_files"] = {"glob": "{root}/runs/*", "kind": "dir"}          # dirs omitted: only stray.txt is a file
    arts["tables_as_dirs"] = {"glob": "{root}/tables/*.parquet", "kind": "dir", "dirs": True}
    arts["broken"] = {"kind": "json"}
    out = LINT.lint_project(p, fx.reg)
    err = _msgs(out, level=LINT.ERROR)
    assert any("artifacts.weird: no loader for kind 'hologram'" in m for m in err)
    assert "artifacts.broken: needs a glob" in err
    warn = _msgs(out, level=LINT.WARN)
    assert any("artifacts.tables_as_dirs" in m and "matches no directories" in m and "dirs = false" in m for m in warn)
    # runs/* without dirs=true still matches stray.txt, so it is not empty and not reported
    assert not any("runs_as_files" in m for m in warn)
    # ... but stray's name now collides with nothing, and run dirs are only in `runs`
    assert not any("'stray'" in m for m in warn)


def test_apps_skip_auto_and_env_values(tmp_path):
    reg = R.Registry(path=tmp_path / "wb.toml",
                     apps={"octave": "auto", "julia_env": "@notebooks", "blender": str(tmp_path / "blender")},
                     defaults={}, projects={})
    out = LINT.lint_apps(reg)
    assert [x.message for x in out] == [f"[apps] blender: {tmp_path / 'blender'} does not exist"]
    (tmp_path / "blender").touch()
    assert LINT.lint_apps(reg) == []


def test_unity_editors_without_editor(tmp_path):
    ed = tmp_path / "editors"
    ed.mkdir()
    reg = R.Registry(path=tmp_path / "wb.toml", apps={"unity_editors": str(ed)}, defaults={}, projects={})
    assert [x.message for x in LINT.lint_apps(reg)] == [f"[apps] unity_editors: no editor under {ed}"]
    (ed / "6000.0.0f1" / "Editor").mkdir(parents=True)
    assert LINT.lint_apps(reg) == []
    p = R.Project(name="u", root=tmp_path, kind="unity", extra={"unity_version": "6000.0.0f1"})
    assert not [x for x in LINT.lint_project(p, reg) if "unity_version" in x.message]


def test_lint_one_project_by_prefix(synthetic_registry):
    out = LINT.lint(synthetic_registry.reg, "be")
    assert {x.project for x in out} <= {"", "beta"}


def test_summary():
    assert LINT.summary([], 3) == "ok: 3 project(s), no findings"
    fs = [LINT.Finding(LINT.ERROR, "a", "x"), LINT.Finding(LINT.WARN, "", "y")]
    assert LINT.summary(fs, 2) == "1 error(s), 1 warning(s) in 2 project(s)"
    assert str(fs[1]).startswith("warning -")


def test_cli_lint(synthetic_registry, capsys):
    rc = cli.main(["lint"])
    out = capsys.readouterr().out
    assert rc == 1                                   # the fixture's [apps] paths do not exist
    assert "error   -" in out and "warning alpha" in out
    assert out.strip().splitlines()[-1].startswith("4 error(s), ")


def test_cli_lint_clean_project_and_strict(synthetic_registry, capsys):
    fx = synthetic_registry
    for key in ("godot", "unity_hub", "blender"):
        Path(fx.reg.apps[key]).parent.mkdir(parents=True, exist_ok=True)
        Path(fx.reg.apps[key]).touch()
    (Path(fx.reg.apps["unity_editors"]) / "6000.0.0f1" / "Editor").mkdir(parents=True)
    Path(fx.reg.defaults["notebooks_dir"]).mkdir()
    assert cli.main(["lint", "beta"]) == 0
    assert capsys.readouterr().out.strip() == "ok: 1 project(s), no findings"
    assert cli.main(["lint", "alpha"]) == 0           # warnings only
    assert cli.main(["lint", "alpha", "--strict"]) == 1
    assert cli.main(["lint", "ghost"]) == 0
    assert "unity_version" not in capsys.readouterr().out   # the editor is now installed


def test_cli_lint_unknown_project(synthetic_registry, capsys):
    assert cli.main(["lint", "zzz"]) == 1
    assert "unknown project" in capsys.readouterr().err


def test_same_stem_within_one_group_is_not_a_clash(tmp_path):
    """Per-session files (sessions/*/gnss.mcap) share a stem inside ONE group: no warning.
    The same stem in TWO groups still warns, naming each group once."""
    root = tmp_path / "rec"
    for sess in ("s1", "s2", "s3"):
        (root / "sessions" / sess).mkdir(parents=True)
        (root / "sessions" / sess / "gnss.mcap").touch()
    (root / "extra").mkdir()
    (root / "extra" / "gnss.mcap").touch()
    reg = R.Registry(path=tmp_path / "wb.toml", apps={}, defaults={}, projects={})
    one = R.Project(name="rec", root=root, kind="python",
                    extra={"artifacts": {"nodes": {"glob": "{root}/sessions/*/gnss.mcap", "kind": "mcap"}}})
    assert not [x for x in LINT.lint_project(one, reg) if "appears in groups" in x.message]
    two = R.Project(name="rec", root=root, kind="python",
                    extra={"artifacts": {"nodes": {"glob": "{root}/sessions/*/gnss.mcap", "kind": "mcap"},
                                         "extra": {"glob": "{root}/extra/*.mcap", "kind": "mcap"}}})
    clash = [x.message for x in LINT.lint_project(two, reg) if "appears in groups" in x.message]
    assert clash == ["artifact name 'gnss' appears in groups extra, nodes; pass group= to catalog.artifacts"]
