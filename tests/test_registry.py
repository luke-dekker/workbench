"""wb.registry: loading workbench.toml and looking projects up."""
from __future__ import annotations

from pathlib import Path

import pytest

from wb import registry as R


def test_load_reads_every_section(synthetic_registry):
    reg = synthetic_registry.reg
    assert reg.path == synthetic_registry.toml
    assert reg.apps["octave"] == "auto"
    assert reg.defaults["marimo_extras"] == ["marimo-studio"]
    assert list(reg.projects) == ["alpha", "alpine", "beta", "ghost"]


def test_project_fields(synthetic_registry):
    p = synthetic_registry.reg.projects["alpha"]
    assert p.name == "alpha"
    assert p.root == synthetic_registry.roots["alpha"]
    assert p.kind == "python"
    assert p.tags == ["ml", "test"]
    assert p.tools == ["code", "term", "marimo"]
    assert p.commands == {}
    assert "artifacts" in p.extra          # anything not a named field lands in extra
    assert "root" not in p.extra


def test_defaults_when_keys_missing(synthetic_registry):
    p = synthetic_registry.reg.projects["alpine"]
    assert p.kind == "python"
    assert p.tags == []
    assert p.commands == {}


def test_exists(synthetic_registry):
    reg = synthetic_registry.reg
    assert reg.projects["alpha"].exists
    assert not reg.projects["ghost"].exists


def test_expand_and_godot_dir(synthetic_registry):
    beta = synthetic_registry.reg.projects["beta"]
    assert beta.expand("{root}/x") == f"{beta.root}/x"
    assert beta.godot_dir == beta.root / "godot"
    assert synthetic_registry.reg.projects["alpha"].godot_dir is None


def test_commands_are_kept_verbatim(synthetic_registry):
    beta = synthetic_registry.reg.projects["beta"]
    assert beta.commands == {"web": "uv run python serve.py --root {root}"}


def test_project_exact_name(synthetic_registry):
    reg = synthetic_registry.reg
    assert reg.project("beta").name == "beta"


def test_project_unique_prefix(synthetic_registry):
    reg = synthetic_registry.reg
    assert reg.project("be").name == "beta"
    assert reg.project("gh").name == "ghost"


def test_project_ambiguous_prefix_raises(synthetic_registry):
    reg = synthetic_registry.reg
    with pytest.raises(KeyError, match="unknown project 'alp'"):
        reg.project("alp")        # alpha and alpine both match


def test_project_unknown_lists_known(synthetic_registry):
    with pytest.raises(KeyError, match="alpha, alpine, beta, ghost"):
        synthetic_registry.reg.project("zzz")


def test_registry_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv(R.REGISTRY_ENV, str(tmp_path / "custom.toml"))
    assert R.registry_path() == tmp_path / "custom.toml"
    monkeypatch.delenv(R.REGISTRY_ENV)
    assert R.registry_path() == R.DEFAULT_REGISTRY
    assert R.DEFAULT_REGISTRY.name == "workbench.toml"


def test_load_uses_env_when_no_path(synthetic_registry):
    assert R.load().path == synthetic_registry.toml


def test_load_empty_registry(tmp_path: Path):
    f = tmp_path / "empty.toml"
    f.write_text("", encoding="utf-8")
    reg = R.load(f)
    assert reg.projects == {} and reg.apps == {} and reg.defaults == {}


def test_load_requires_root(tmp_path: Path):
    f = tmp_path / "bad.toml"
    f.write_text('[projects.x]\nkind = "python"\n', encoding="utf-8")
    with pytest.raises(KeyError):
        R.load(f)
