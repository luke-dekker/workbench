# workbench

One registry, many launchers. `workbench.toml` lists every project, the tools that make
sense for it, and the data it produces. The **Workbench** taskbar button opens a window listing
every notebook by project; `wb` does the same from the shell; `wb.catalog` makes every
project's data reachable from any notebook.

## Quick start

1. Click **Workbench** on the taskbar (or Start menu). If it is not pinned: Start menu >
   right-click Workbench > Pin to taskbar.
2. Right-click a project > *New marimo notebook in <project>*. Name it. A browser tab opens with
   the notebook running inside that project's environment.
3. In the notebook, the last cell runs `catalog.show("<project>")` and lists that project's
   data. `catalog.snippet(a)` prints the code that loads any row. The snippets panel on the
   left has ready-made `Workbench:` cells.
4. Double-click any notebook in the window to reopen it later.

## Command line

    wb list                         # projects (! = root missing)
    wb tools node-tool              # what a project offers
    wb open node-tool web           # run its [commands].web in a Windows Terminal tab
    wb open sceneforge godot        # Godot editor on sceneforge/godot
    wb open node-tool marimo notebooks/foo.py   # marimo inside node-tool's uv env (+studio, +lens)
    wb open workbench pluto         # Pluto home page from the shared @notebooks Julia env
    wb open unity-app unity          # Unity editor matching ProjectSettings/ProjectVersion.txt
    wb new unity-app                 # create a missing project root
    wb doctor                       # check every executable the registry points at
    wb gui                          # the launcher window (what the taskbar shortcut opens)
    wb shortcut                     # Start-menu shortcut for the window (then right-click > Pin to taskbar)
    wb sleuth <project>             # where does this project write outputs? suggests [artifacts] lines
    wb tray                         # optional system-tray variant (wb shortcut --tray)

## Install / update

Copy `workbench.example.toml` to `workbench.toml` (gitignored) and edit the paths; or point
`WORKBENCH_TOML` at a registry kept elsewhere. Register the snippets for marimo once in
`~/.config/marimo/marimo.toml`: `[snippets] custom_paths = ["<clone-dir>/snippets"]`.

    uv tool install --editable <clone-dir>      # `wb` on PATH; edits to wb/ are live
    uv sync                                                  # workbench env: core (numpy, pyarrow, safetensors, mcap) + dev group (marimo, studio, lens, jupyterlab, octave-kernel, polars)
    julia --project=@notebooks -e 'using Pkg; Pkg.develop(path="<clone-dir>/julia/Workbench")'   # once; the Julia bridge

## Layers

1. **Environments.** uv for Python (marimo is a per-project dep so it matches that project's torch).
   juliaup for Julia; Pluto, IJulia, PythonCall, Arrow live in the shared `@notebooks` env.
   winget for apps (Octave). Jupyter kernels: python3, julia-1.12, octave.
2. **Interop by format, not by bridge.** See `notebooks/README.md`. Proof in `notebooks/interop/`:
   `make_data.py` writes safetensors + Arrow + Parquet; `view.py` (marimo) and `read_data.jl`
   (pure Julia, plus PythonCall against `.venv`) read the same bytes and agree.
3. **Launcher.** `wb/registry.py` loads the TOML, `wb/launch.py` knows how to start each tool
   and how to find and create notebooks. Front ends: `wb/launcher.py` (the window),
   `wb/cli.py` (shell), `wb/tray.py` (optional tray icon, not the default).
4. **Catalog.** `wb/catalog.py` turns the `[artifacts]` globs into something every notebook can
   query and load; `julia/Workbench` is the same thing for Julia. `wb/sleuth.py` finds where a
   project writes so the globs can be filled in.

## The window

One list: every notebook the registry's projects contain, grouped by project.

- **Double-click / Enter** opens a notebook in the right tool (marimo, Jupyter, Pluto, Octave)
  inside that project's env.
- **Right-click** a project header or one of its notebooks:
  *New marimo / Pluto / Jupyter notebook in <that project>* (lands in `<root>/notebooks/`),
  the project's tools (code, term, Godot, Unity, web, ...), open folder, sleuth outputs.
- **Filter** box matches on path, project and kind. **F5** rescans.
- The `workbench` project doubles as the scratch home: `notebooks/` holds marimo, Julia and
  Octave scratch files and they show up under it like any other project's notebooks.
- Notebook servers (marimo, Jupyter, Pluto) start **hidden**: no terminal, the browser tab just
  appears. Output goes to `logs/<server>.log`; right-click anywhere for *Stop notebook servers*
  and *Open server logs folder*. Prefer a visible terminal tab? Set `servers = "terminal"` under
  `[defaults]` in `workbench.toml`. Shells, Julia REPLs and the node-tool `web` command still get
  a Windows Terminal tab because they are interactive.
- The pinned button and the window share one taskbar entry: the shortcut targets the base
  `pythonw.exe` (the window needs only the stdlib) and both carry the AppUserModelID
  `Workbench.Launcher`, written into the .lnk by `wb shortcut` via pywin32.

## The catalog: data from every project, in any notebook

`wb.catalog` turns the registry into a data catalog. It is layered into every project env the
launcher opens (`uv run --with-editable workbench`), so this works in any marimo / Jupyter
notebook, in a script, and from Pluto through PythonCall:

    from wb import catalog
    catalog.show()                                   # table of every artifact (nothing loaded)
    catalog.show("fieldrec")
    a = catalog.latest("fieldrec", kind="mcap", group="sessions")
    sess = catalog.load(a)                           # {topic: pyarrow.Table}
    t = catalog.load(catalog.latest("node-tool", kind="safetensors"))   # {name: ndarray}
    print(catalog.snippet(a))                        # the code that loads a, to paste

Artifacts are declared per project in `workbench.toml`:

    [projects.fieldrec.artifacts]
    sessions = { glob = "<data-root>/sessions/*/*.mcap", kind = "mcap" }
    [projects.sceneforge.artifacts]
    runs = { glob = "{root}/runs/*", kind = "dir", dirs = true }

Loaders by kind: `mcap` (fieldrec JSON-encoded topics -> Arrow tables), `safetensors`, `torch`,
`parquet`, `arrow`, `csv`, `json`, `jsonl`, `npz`, `text`, `png`, `file` (hands back the Path),
`dir` (run / session folder). Add one with `@catalog.loader("kind", snippet_template)`.
Names that repeat within a project (fieldrec's per-node `gnss` / `can` / `video`) get snippets
that use the full path via `catalog.load_path(path, kind)`.

Discovery inside marimo: the new-notebook stub ends with a `catalog.show("<project>")` cell, and
the **snippets panel** (left sidebar) lists `Workbench: ...` snippets from `snippets/`
(registered in `~/.config/marimo/marimo.toml`). Autocomplete on `catalog.` shows the docstrings.

### From Julia (Pluto, IJulia, scripts)

`julia/Workbench` is a Julia package (developed into the `@notebooks` env) that wraps the same
catalog through PythonCall. The launcher sets `JULIA_PYTHONCALL_EXE` to the workbench venv and
`JULIA_CONDAPKG_BACKEND=Null` for every Pluto / Julia launch, so this just works there:

    using Workbench
    Workbench.show("fieldrec")                      # Vector of NamedTuples (Pluto renders it)
    a    = Workbench.latest("fieldrec"; kind="mcap", group="sessions")
    sess = Workbench.load(a)                        # Dict{String, Arrow.Table}, one per topic
    w    = Workbench.load(Workbench.latest("node-tool"; kind="safetensors"))   # Dict{String, Array}
    Workbench.snippet(a)

Arrow tables cross over as IPC bytes (no per-element conversion). New Pluto stubs end with a
`Workbench.show("<project>")` cell, like the marimo ones.

### Finding where a project writes: `wb sleuth`

    wb sleuth struct-sim            # on-disk data files by folder, write calls in the code, suggested TOML
    wb sleuth struct-sim --apply    # append the suggestion (commented) to workbench.toml
    wb sleuth                       # every project

Same thing from the window: right-click a project > **sleuth outputs**. The suggestion is a
starting point; projects that take output paths from the CLI (jointbus, struct-sim) need a
convention, and the registry comments record which one was chosen.

## Unity + Godot fast loop

`docs/FAST_LOOP.md` is the plan and the **TODO list** (what is done, what is unverified, what is
blocked). Short version:

    wb new unity-app                      # Unity project from templates/unity + godot/ mirror + shared/ junctions,
                                         # then Workbench.Setup headless: packages, play-mode options, bootstrap scene
    wb open unity-app setup|build|deploy  # headless Unity in a terminal tab (deploy = build + adb install + logcat)
    wb open unity-app godot_run           # run the Godot mirror's main scene, no editor
    wb unity unity-app build windows      # same thing blocking, in this shell

Godot `.tscn` files are listed in the window next to notebooks; double-click runs the scene directly.
Inside Unity the same code sits under the **Workbench** menu (Setup project, Build Android/Windows,
Play from Bootstrap). Headless runs log to `logs/unity-<project>.log`.

## Agent tooling for marimo

- marimo-studio and marimo-lens are Python packages and are already in the env.
- marimo-pair is a Claude Code plugin, installed from inside Claude Code:
  `/plugin marketplace add marimo-team/marimo-pair` then `/plugin install marimo-pair@marimo-pair`.
  Start notebooks with `--no-token` (wb does) so pair can discover them.
- marimo-team/skills has more agent skills: `npx skills add marimo-team/skills`.

## Files

    workbench.toml      the registry: [apps], [defaults], [projects.<name>] (+ .commands, .artifacts)
    wb/                 the package (stdlib-only for the window; catalog needs numpy/pyarrow/safetensors/mcap)
    julia/Workbench/    Julia package wrapping the catalog via PythonCall
    snippets/           marimo snippets (registered in ~/.config/marimo/marimo.toml)
    notebooks/          scratch notebooks + the interop proof (see notebooks/README.md)
    assets/             window icon (generated) and the .aumid marker written by `wb shortcut`
    logs/               hidden notebook servers log here (git-ignored)

## Registry reference

    [apps]        godot, unity_hub, unity_editors, blender, octave ("auto"), julia_env
    [defaults]    marimo_extras, notebooks_dir, servers ("hidden" | "terminal")
    [projects.X]  root, kind, tags, tools, godot_dir, unity_version
    [projects.X.commands]   name = "shell command run in root in a terminal tab"  (becomes a tool)
    [projects.X.artifacts]  group = { glob = "...", kind = "...", dirs = true? }  ({root} expands)
