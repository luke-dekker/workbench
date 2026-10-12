"""wb.launch: launchers return argv without starting anything; notebook discovery and creation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wb import launch as L

MARIMO_NB = 'import marimo\n\n__generated_with = "0.25.0"\napp = marimo.App()\n'
MARIMO_NB_PEP723 = '# /// script\n# dependencies = ["marimo"]\n# ///\nimport marimo\napp = marimo.App()\n'
PLUTO_NB = "### A Pluto.jl notebook ###\n# v0.20.0\n\nusing Markdown\n"


# ---------------------------------------------------------- notebook_kind
@pytest.mark.parametrize("name, body, kind", [
    ("a.py", MARIMO_NB, "marimo"),
    ("b.py", MARIMO_NB_PEP723, "marimo"),
    ("c.py", 'x = "marimo.App("\n', None),              # mentions it as a string, is not one
    ("d.py", "import marimo\nprint(1)\n", None),          # imports it but has no App
    ("e.ipynb", "{}", "jupyter"),
    ("f.jl", PLUTO_NB, "pluto"),
    ("g.jl", "using Foo\n", None),
    ("h.m", "disp(1)\n", "octave"),
    ("i.tscn", "[gd_scene]\n", "scene"),
    ("j.txt", "hi\n", None),
])
def test_notebook_kind(tmp_path: Path, name, body, kind):
    f = tmp_path / name
    f.write_text(body, encoding="utf-8")
    assert L.notebook_kind(f) == kind


def test_notebook_kind_missing_file(tmp_path: Path):
    assert L.notebook_kind(tmp_path / "nope.py") is None


# --------------------------------------------------------- find_notebooks
def test_find_notebooks(synthetic_registry):
    p = synthetic_registry.reg.projects["beta"]
    root = p.root
    (root / "top.py").write_text(MARIMO_NB, encoding="utf-8")
    (root / "notebooks").mkdir()
    (root / "notebooks" / "nb.ipynb").write_text("{}", encoding="utf-8")
    (root / "notebooks" / "plain.py").write_text("print(1)\n", encoding="utf-8")
    (root / "godot" / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    for skip in (".venv", "__marimo__", "runs"):
        (root / skip).mkdir()
        (root / skip / "hidden.py").write_text(MARIMO_NB, encoding="utf-8")
    deep = root / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    (deep / "deep.py").write_text(MARIMO_NB, encoding="utf-8")
    (root / "a" / "b" / "ok.py").write_text(MARIMO_NB, encoding="utf-8")

    found = L.find_notebooks(p)
    rel = [(f.relative_to(root).as_posix(), k) for f, k in found]
    assert rel[0] == ("top.py", "marimo")                        # shallowest first
    assert ("a/b/ok.py", "marimo") in rel
    assert ("godot/main.tscn", "scene") in rel
    assert ("notebooks/nb.ipynb", "jupyter") in rel
    assert not any("plain.py" in r or "hidden.py" in r or "deep.py" in r for r, _ in rel)


def test_find_notebooks_missing_root(synthetic_registry):
    assert L.find_notebooks(synthetic_registry.reg.projects["ghost"]) == []


# ------------------------------------------------------------ package_name
def test_package_name(synthetic_registry):
    p = synthetic_registry.reg.projects["beta"]
    assert L.package_name(p) is None                                # no pyproject
    (p.root / "pyproject.toml").write_text('[project]\nname = "my-pkg"\n', encoding="utf-8")
    assert L.package_name(p) is None                                # no package dir
    (p.root / "my_pkg").mkdir()
    (p.root / "my_pkg" / "__init__.py").write_text("", encoding="utf-8")
    assert L.package_name(p) == "my_pkg"
    (p.root / "pyproject.toml").write_text("not = [toml", encoding="utf-8")
    assert L.package_name(p) is None


def test_has_uv_project(synthetic_registry):
    p = synthetic_registry.reg.projects["beta"]
    assert not L.has_uv_project(p)
    (p.root / ".venv").mkdir()
    assert L.has_uv_project(p)


# ------------------------------------------------------------- launchers
def test_code(synthetic_registry, no_spawn):
    p, reg = synthetic_registry.reg.projects["alpha"], synthetic_registry.reg
    argv = L.code(p, reg, ["--new-window"])
    assert argv[1:] == [str(p.root), "--new-window"]
    assert no_spawn.calls[0]["argv"] == argv


def test_term_runs_in_project_root(synthetic_registry, no_spawn):
    p, reg = synthetic_registry.reg.projects["alpha"], synthetic_registry.reg
    argv = L.term(p, reg, ["echo", "hi"])
    assert "echo hi" in argv
    assert no_spawn.calls[0]["cwd"] == str(p.root)


def test_command_launcher(synthetic_registry, no_spawn):
    p, reg = synthetic_registry.reg.projects["beta"], synthetic_registry.reg
    argv = L.command("web")(p, reg, ["--port", "8"])
    assert f"uv run python serve.py --root {p.root} --port 8" in argv   # {root} expanded, args appended
    with pytest.raises(L.LaunchError, match="no command 'nope'"):
        L.command("nope")(p, reg, [])


def test_resolve_prefers_project_command(synthetic_registry):
    p = synthetic_registry.reg.projects["beta"]
    assert L.resolve(p, "web").__name__ == "run"
    assert L.resolve(p, "code") is L.code
    with pytest.raises(L.LaunchError, match="offers: web, code, godot, godot_run"):
        L.resolve(p, "nope")


def test_launch_missing_root(synthetic_registry, no_spawn):
    reg = synthetic_registry.reg
    with pytest.raises(L.LaunchError, match="does not exist"):
        L.launch(reg.projects["ghost"], reg, "code")
    L.launch(reg.projects["ghost"], reg, "unity_hub")               # the one tool allowed without a root
    assert no_spawn.calls[0]["argv"] == [reg.apps["unity_hub"]]


def test_marimo_argv(synthetic_registry, no_spawn):
    p, reg = synthetic_registry.reg.projects["alpha"], synthetic_registry.reg
    argv = L.marimo(p, reg, [])
    assert argv == ["marimo", "edit", "--no-token", str(p.root / "notebooks")]   # no uv project: global marimo
    assert (p.root / "notebooks").is_dir()
    (p.root / "pyproject.toml").write_text("[project]\nname='alpha'\n", encoding="utf-8")
    argv = L.marimo(p, reg, ["nb.py"])
    assert argv[:4] == ["uv", "run", "--with-editable", str(L.WORKBENCH_ROOT)]
    assert "--with" in argv and "marimo-studio" in argv               # marimo_extras from [defaults]
    assert argv[-4:] == ["marimo", "edit", "--no-token", "nb.py"]


def test_server_hidden_logs_and_tracks(synthetic_registry, no_spawn):
    p, reg = synthetic_registry.reg.projects["alpha"], synthetic_registry.reg
    L.jupyter(p, reg, [])
    call = no_spawn.calls[0]
    assert call["argv"] == ["jupyter", "lab"]
    assert call["cwd"] == str(p.root)
    assert (L.LOG_DIR / "jupyter-alpha.log").exists()
    assert [t for t, _ in L.running_servers()] == ["jupyter-alpha"]
    assert L.stop_servers() == 1
    assert L.running_servers() == []


def test_server_terminal_mode(synthetic_registry, no_spawn):
    reg = synthetic_registry.reg
    reg.defaults["servers"] = "terminal"
    argv = L.jupyter(reg.projects["alpha"], reg, [])
    assert "jupyter lab" in argv
    assert L.running_servers() == []


def test_pluto_and_julia_env(synthetic_registry, no_spawn):
    p, reg = synthetic_registry.reg.projects["alpha"], synthetic_registry.reg
    argv = L.pluto(p, reg, [])
    assert argv[:2] == ["julia", "--project=@notebooks"]
    env = no_spawn.calls[0]["env"]
    assert env["JULIA_CONDAPKG_BACKEND"] == "Null"
    assert env["JULIA_PYTHONCALL_EXE"].startswith(str(L.WORKBENCH_ROOT))


def test_julia_prefers_project_toml(synthetic_registry, no_spawn):
    p, reg = synthetic_registry.reg.projects["alpha"], synthetic_registry.reg
    assert '--project="@notebooks"' in " ".join(L.julia(p, reg, []))
    (p.root / "Project.toml").write_text("", encoding="utf-8")
    assert f'--project="{p.root}"' in " ".join(L.julia(p, reg, ["-e", "1"]))


def test_octave_missing(synthetic_registry, no_spawn, monkeypatch):
    reg = synthetic_registry.reg
    monkeypatch.setattr(L, "find_octave", lambda reg: None)
    with pytest.raises(L.LaunchError, match="Octave not found"):
        L.octave(reg.projects["alpha"], reg, [])


def test_find_octave_configured_path(synthetic_registry, tmp_path):
    reg = synthetic_registry.reg
    exe = tmp_path / "octave-launch.exe"
    exe.write_text("", encoding="utf-8")
    reg.apps["octave"] = str(exe)
    assert L.find_octave(reg) == str(exe)


def test_godot_editor(synthetic_registry, no_spawn):
    reg = synthetic_registry.reg
    beta, alpha = reg.projects["beta"], reg.projects["alpha"]
    assert L.godot(beta, reg, []) == [reg.apps["godot"], "--path", str(beta.root / "godot"), "-e"]
    assert L.godot(alpha, reg, []) == [reg.apps["godot"], "-p"]        # no project.godot: project manager


def test_godot_run(synthetic_registry, no_spawn):
    reg = synthetic_registry.reg
    beta = reg.projects["beta"]
    gdir = beta.root / "godot"
    (gdir / "scenes").mkdir()
    (gdir / "scenes" / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    assert L.godot_run(beta, reg, []) == [reg.apps["godot"], "--path", str(gdir)]
    argv = L.godot_run(beta, reg, ["scenes/main.tscn", "--verbose"])
    assert argv == [reg.apps["godot"], "--path", str(gdir), "res://scenes/main.tscn", "--verbose"]
    argv = L.godot_run(beta, reg, ["godot/scenes/main.tscn"])           # relative to the project root too
    assert argv[-1] == "res://scenes/main.tscn"
    with pytest.raises(L.LaunchError, match="scene not found"):
        L.godot_run(beta, reg, ["nope.tscn"])
    with pytest.raises(L.LaunchError, match="no project.godot"):
        L.godot_run(reg.projects["alpha"], reg, [])


def test_godot_project_dir(synthetic_registry):
    gdir = synthetic_registry.roots["beta"] / "godot"
    (gdir / "x").mkdir()
    assert L.godot_project_dir(gdir / "x" / "s.tscn") == gdir
    assert L.godot_project_dir(gdir / "x") == gdir
    assert L.godot_project_dir(synthetic_registry.roots["alpha"]) is None


def test_unity(synthetic_registry, no_spawn, tmp_path):
    reg = synthetic_registry.reg
    alpha = reg.projects["alpha"]
    with pytest.raises(L.LaunchError, match="no ProjectSettings"):
        L.unity(alpha, reg, [])
    (alpha.root / "ProjectSettings").mkdir()
    (alpha.root / "ProjectSettings" / "ProjectVersion.txt").write_text(
        "m_EditorVersion: 2022.3.1f1\nm_EditorVersionWithRevision: 2022.3.1f1 (abc)\n", encoding="utf-8")
    assert L.unity_project_version(alpha.root) == "2022.3.1f1"
    with pytest.raises(L.LaunchError, match="Unity 2022.3.1f1 not installed"):
        L.unity(alpha, reg, [])
    exe = L.unity_exe(reg, "2022.3.1f1")
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    assert L.unity(alpha, reg, ["-batchmode"]) == [str(exe), "-projectPath", str(alpha.root), "-batchmode"]


def test_unity_version_from_registry(synthetic_registry):
    ghost = synthetic_registry.reg.projects["ghost"]
    assert L.unity_project_version(ghost.root) is None
    assert ghost.extra["unity_version"] == "6000.0.0f1"


def test_unity_headless_tools_go_through_wb(synthetic_registry, no_spawn, monkeypatch):
    reg = synthetic_registry.reg
    alpha = reg.projects["alpha"]
    monkeypatch.setattr(L.shutil, "which", lambda name: None)
    argv = L.unity_build(alpha, reg, ["android"])
    cmd = " ".join(argv)
    assert "wb unity alpha build android" in cmd
    assert "--directory" in cmd                                      # falls back to uv run when wb is not on PATH
    assert "wb unity alpha setup" in " ".join(L.unity_setup(alpha, reg, []))
    assert "wb unity alpha deploy" in " ".join(L.unity_deploy(alpha, reg, []))


def test_blender_and_explorer(synthetic_registry, no_spawn):
    reg = synthetic_registry.reg
    alpha = reg.projects["alpha"]
    assert L.blender(alpha, reg, ["f.blend"]) == [reg.apps["blender"], "f.blend"]
    assert L.explorer(alpha, reg, []) == ["explorer", str(alpha.root)]


def test_builtin_covers_registry_tools(synthetic_registry):
    for p in synthetic_registry.reg.projects.values():
        for t in p.tools:
            assert t in L.BUILTIN or t in p.commands, (p.name, t)


# ---------------------------------------------------------- new_notebook
def test_new_marimo_notebook(synthetic_registry, no_spawn):
    reg = synthetic_registry.reg
    beta = reg.projects["beta"]
    (beta.root / "pyproject.toml").write_text('[project]\nname = "beta"\n', encoding="utf-8")
    (beta.root / "beta").mkdir()
    (beta.root / "beta" / "__init__.py").write_text("", encoding="utf-8")
    argv = L.new_notebook(beta, reg, "marimo", "My Analysis!")
    f = beta.root / "notebooks" / "My_Analysis.py"
    assert f.exists()
    body = f.read_text(encoding="utf-8")
    assert L.notebook_kind(f) == "marimo"
    assert 'catalog.show("beta")' in body
    assert "import beta" in body                                      # package import cell
    assert "# My Analysis!" in body
    assert "{project}" not in body and "{name}" not in body and "{import_cell}" not in body
    assert argv[-1] == str(f)                                         # opened in marimo
    # creating it again keeps the file
    f.write_text(body + "\n# edited", encoding="utf-8")
    L.new_notebook(beta, reg, "marimo", "My Analysis!")
    assert f.read_text(encoding="utf-8").endswith("# edited")


def test_new_marimo_notebook_without_package(synthetic_registry, no_spawn):
    reg = synthetic_registry.reg
    L.new_notebook(reg.projects["alpha"], reg, "marimo", "x")
    body = (reg.projects["alpha"].root / "notebooks" / "x.py").read_text(encoding="utf-8")
    assert "{import_cell}" not in body and "{pkg}" not in body


def test_new_pluto_notebook(synthetic_registry, no_spawn):
    reg = synthetic_registry.reg
    argv = L.new_notebook(reg.projects["alpha"], reg, "pluto", "sim")
    f = reg.projects["alpha"].root / "notebooks" / "sim.jl"
    body = f.read_text(encoding="utf-8")
    assert L.notebook_kind(f) == "pluto"
    assert 'Workbench.show("alpha")' in body
    assert "{cell" not in body
    assert argv[-1] == f.as_posix()
    assert argv[3] == "using Pluto; Pluto.run(notebook=ARGS[1])"


def test_new_jupyter_notebook(synthetic_registry, no_spawn):
    reg = synthetic_registry.reg
    L.new_notebook(reg.projects["alpha"], reg, "jupyter", "nb")
    f = reg.projects["alpha"].root / "notebooks" / "nb.ipynb"
    nb = json.loads(f.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4 and nb["cells"][0]["source"] == ["# nb"]
    assert no_spawn.calls[-1]["argv"][-1] == str(f)


def test_new_notebook_unknown_kind(synthetic_registry, no_spawn):
    reg = synthetic_registry.reg
    with pytest.raises(L.LaunchError, match="unknown notebook kind"):
        L.new_notebook(reg.projects["alpha"], reg, "rmarkdown", "x")


def test_new_notebook_in_scratch_project_lands_at_root(synthetic_registry, no_spawn):
    """A project whose root sits under [defaults].notebooks_dir gets the file at its root."""
    reg = synthetic_registry.reg
    scratch = Path(reg.defaults["notebooks_dir"]) / "pad"
    scratch.mkdir(parents=True)
    from wb.registry import Project
    p = Project("pad", scratch, "python")
    L.new_notebook(p, reg, "marimo", "quick")
    assert (scratch / "quick.py").exists()
    assert not (scratch / "notebooks").exists()


def test_slug():
    assert L._slug("My Analysis!") == "My_Analysis"
    assert L._slug("  a/b  ") == "a_b"
    assert L._slug("").startswith("nb_")


# --------------------------------------------------------- open_notebook
def test_open_notebook_dispatch(synthetic_registry, no_spawn, monkeypatch):
    reg = synthetic_registry.reg
    beta = reg.projects["beta"]
    nb = beta.root / "nb.py"
    nb.write_text(MARIMO_NB, encoding="utf-8")
    assert L.open_notebook(beta, reg, nb)[-1] == str(nb)
    scene = beta.root / "godot" / "main.tscn"
    scene.write_text("[gd_scene]\n", encoding="utf-8")
    assert L.open_notebook(beta, reg, scene)[-1] == "res://main.tscn"
    m = beta.root / "s.m"
    m.write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(L, "find_octave", lambda reg: "octave")
    assert L.open_notebook(beta, reg, m) == ["octave", "--gui", "--persist", str(m)]
    other = beta.root / "readme.txt"
    other.write_text("", encoding="utf-8")
    with pytest.raises(L.LaunchError, match="readme.txt is not a notebook"):
        L.open_notebook(beta, reg, other)
