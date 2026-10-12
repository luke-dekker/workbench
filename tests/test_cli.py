"""wb.cli: the subcommands that run headless, driven through main(argv)."""
from __future__ import annotations

import pytest

from wb import cli


def test_list(synthetic_registry, capsys):
    assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "  alpha" in out and "ml,test" in out
    assert "! ghost" in out
    assert "root missing: ghost" in out


def test_tools(synthetic_registry, capsys):
    assert cli.main(["tools", "beta"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].split() == ["web", "command"]
    assert out[1].split() == ["code", "builtin"]


def test_unknown_project_is_an_error(synthetic_registry, capsys):
    assert cli.main(["tools", "zzz"]) == 1
    assert "wb: " in capsys.readouterr().err


def test_open_prints_argv(synthetic_registry, no_spawn, capsys):
    assert cli.main(["open", "alpha", "code", "--reuse-window"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("[alpha:code] ")
    assert "--reuse-window" in out
    assert len(no_spawn.calls) == 1


def test_open_defaults_to_first_tool(synthetic_registry, no_spawn, capsys):
    assert cli.main(["open", "be"]) == 0                              # prefix match; first tool is `web`
    assert capsys.readouterr().out.startswith("[beta:web] ")


def test_open_launch_error(synthetic_registry, no_spawn, capsys):
    assert cli.main(["open", "ghost", "code"]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_help_runs(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
    assert "wb list" in capsys.readouterr().out


def test_sleuth_report(synthetic_registry, capsys):
    assert cli.main(["sleuth", "alpha"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# sleuth: alpha")
    assert "[projects.alpha.artifacts]" in out


def test_sleuth_apply_appends_commented_block(synthetic_registry, capsys):
    before = synthetic_registry.toml.read_text(encoding="utf-8")
    assert cli.main(["sleuth", "alpha", "--apply"]) == 0
    after = synthetic_registry.toml.read_text(encoding="utf-8")
    assert after.startswith(before)
    added = after[len(before):]
    assert "# --- wb sleuth suggestion" in added
    assert all(ln.startswith("#") for ln in added.strip().splitlines())
    assert "appended commented suggestion for alpha" in capsys.readouterr().out
    # the registry still parses
    from wb import registry as R
    assert list(R.load(synthetic_registry.toml).projects) == ["alpha", "alpine", "beta", "ghost"]


def test_sleuth_all_skips_missing_roots(synthetic_registry, capsys):
    assert cli.main(["sleuth"]) == 0
    out = capsys.readouterr().out
    assert "# sleuth: alpha" in out and "# sleuth: beta" in out
    assert "# sleuth: ghost" not in out
