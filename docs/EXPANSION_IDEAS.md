# Expansion ideas, ranked

As of 2026-10-12. A read of the README, `workbench.example.toml`, `wb/registry.py`, `wb/catalog.py`,
`wb/launch.py`, `wb/sleuth.py`, `wb/cli.py`, `julia/Workbench`, `snippets/` and `docs/FAST_LOOP.md`.
No code was changed for this write-up.

Ranking is payoff divided by effort. Effort: S (hours), M (a day or two), L (a week or more).
Payoff: how much the daily loop (open project, find data, change a thing, see it run) gets
shorter, and how many other ideas it unlocks. Items already on the `docs/FAST_LOOP.md` TODO
list are marked "FAST_LOOP".

The five to do first: a test suite, `catalog.save`, an MCP server over the catalog, `wb lint`,
and generated snippets. Each is a day or less and makes the rest of the list cheaper.

## Tier 1: small effort, high payoff

| # | Idea | What it is | Effort | Payoff | Why now |
| --- | --- | --- | --- | --- | --- |
| 1 | Test suite | `tests/` with a synthetic registry in a temp dir: registry load and prefix match, catalog glob and sort, every loader on a tiny generated file, `snippet()` round trip, `notebook_kind` detection, sleuth suggestion on a fake tree. Launchers already return argv, so they test without spawning. | S | High | There are no tests today. Every other idea touches `catalog.py` or `launch.py`, and the catalog is layered into every project env, so a regression breaks all notebooks at once. |
| 2 | `catalog.save(obj, project, group)` | Write a table, dict of arrays, or JSON into a project's artifact group in the contract format (parquet, safetensors, json) and return the `Artifact`. Chooses the path from the group's glob. | S | High | The catalog is read-only, so notebook results leave the catalog the moment they exist. Closes the loop and makes a Julia `Workbench.save` a one-liner. |
| 3 | `wb mcp` | A stdio MCP server exposing `catalog.projects`, `show`, `snippet`, `load` (summary only: shape, columns, row count), plus `wb open`. One file on top of the existing functions. | S | High | marimo-pair and Claude Code already sit in the loop. An agent that can ask "what data does fieldrec have and how do I load it" skips the paste-the-snippet step. |
| 4 | `wb lint` | Walk the registry: unknown tools, globs that match nothing, app paths that do not exist, missing roots, duplicate artifact names within a project. Fold the FAST_LOOP `wb doctor` additions (adb, Android module, Godot export templates, git-lfs) in here or into doctor. | S | Medium | Dead globs fail silently: `catalog.latest` raises `LookupError` with no hint that the glob is wrong. Sleuth suggestions get pasted and never verified. |
| 5 | Generated snippets | `wb snippets` regenerates `snippets/` from the registry: one marimo snippet per artifact group using the `catalog.snippet` templates, plus the hand-written general ones. | S | Medium | The five snippets are hand-maintained and name specific projects. New artifact groups never get one. |
| 6 | `wb add <path>` | Detect kind (pyproject, Project.toml, project.godot, ProjectSettings), pick default tools, run sleuth, append a complete `[projects.X]` block. | S | Medium | Registering a project is the only onboarding step still done by hand. |
| 7 | Artifact index cache | Cache `artifacts()` results per glob keyed on directory mtime, invalidated by F5 and `wb lint`. | S | Medium | Session globs run on every `show`, `latest`, `find` and `snippet` call; `snippet()` globs twice. Noticeable once sessions number in the hundreds. |

## Tier 2: medium effort, worth planning

| # | Idea | What it is | Effort | Payoff | Notes |
| --- | --- | --- | --- | --- | --- |
| 8 | Provenance sidecar | `catalog.save` and `wb run` write `<artifact>.wb.json` beside each output: project, notebook or command, git commit, timestamp, input artifacts. `show()` gains a `from` column; `catalog.lineage(a)` walks it. | M | High | Depends on #2. Answers "which notebook made this parquet" without a database. |
| 9 | `wb run <project> <command>` | Run a registry command blocking, tee stdout and stderr to `logs/`, record start, end and exit code, register a new run folder as a `dir` artifact. | M | High | jointbus and struct-sim take output paths from the CLI and have no convention. A run wrapper is where the convention lives. Pairs with #8. |
| 10 | More loader kinds | `glb`/`gltf` (via `pygltflib`: node tree, mesh counts), `tscn` and `unity` (node names), `mcap` with protobuf and ROS 2 encodings, `mp4` (frame count, duration, first frame), `las`/`ply` point clouds (numpy). | M | Medium | glTF, video and point clouds are `file` kind today: listed but opaque. sceneforge runs are mostly these. |
| 11 | Godot headless export | `wb open <project> godot_export [preset]` with `--headless --export-release`; `wb lint` checks export templates and `export_presets.cfg`. FAST_LOOP. | M | Medium | Completes the Godot half of the build loop. Blocked on export templates being installed. |
| 12 | Unity asmdefs in the template | `Assets/Scripts/Game.asmdef` and the editor asmdef from `Setup.cs`. FAST_LOOP. | M | High | A script edit recompiles one assembly instead of the project. Largest remaining free Unity speedup after Enter Play Mode Options. |
| 13 | XR Simulation and XR plug-in from Setup.cs | Enable the ARCore loader for Android and XR Simulation in the editor without the manual tick. FAST_LOOP. | M | Medium | Most AR iterations never touch a phone once this is in. |
| 14 | Window: running servers and recents | Show tracked notebook servers with port and log tail, a most-recent list at the top, keyboard open on Enter in the filter. | M | Medium | The window is the daily entry point. Servers start hidden, so a stuck one is invisible. |
| 15 | `wb watch <project>` | Poll an artifact group (or use `watchdog`) and print the snippet when a new file lands. Optional toast on Windows. | M | Low | Useful for fieldrec sessions arriving from a recorder, niche otherwise. |
| 16 | Platform layer for launch.py | `_in_terminal`, `_spawn`, `stop_servers`, `julia_env` and `cmd_shortcut` are Windows-only. Put them behind a small `platform.py` with a Linux and macOS path. | M | Low now | Only worth it if a second machine enters the picture. Flagged because it blocks running the test suite in CI on Linux. |

## Tier 3: big bets

| # | Idea | What it is | Effort | Payoff | Notes |
| --- | --- | --- | --- | --- | --- |
| 17 | Live tuning channel | A small WebSocket listener in dev builds of both engines, a `wb/live.py` client, and a marimo snippet that pushes parameters or catalog data into the running scene. Change a value, see it, no rebuild. FAST_LOOP. | L | High | The single biggest cut to the engine loop. The contract table in `notebooks/README.md` already names WebSocket + JSON as the live format. |
| 18 | `scene.json` to Unity prefab and Godot `.tscn` | An exporter from the sceneforge GeoPose scene description to both engines, driven by `wb`, writing into `shared/`. FAST_LOOP. | L | High | Needed by Paired Reality regardless. The Godot mirror and the Unity build start from one source instead of two hand-built scenes. |
| 19 | Run comparison | `catalog.compare(a, b)` for two `dir` artifacts: file lists, sizes, JSON diffs, table schemas, and a marimo view. | L | Medium | sceneforge runs and jointbus policy folders are the use case. Worth it after #8 gives runs a provenance record. |
| 20 | Pure C# game logic outside Unity | A plain .NET class library under the Unity template, referenced by the asmdef, tested with `dotnet test` from `wb`. FAST_LOOP. | L | Medium | Logic tests run in seconds without the editor. Payoff grows with the amount of non-engine code. |
| 21 | Blender save handler to `shared/` | A Blender add-on that re-exports glTF into `shared/` on save, starting from the sceneforge Blender bridge; a glTF round-trip proof with screenshots. FAST_LOOP. | L | Medium | Closes the asset half of the Unity and Godot loop. |

## Parking lot

- Remote data roots (NAS, S3) via fsspec. All data is local today.
- Octave access to the catalog. Possible through the Python bridge; no Octave project declares artifacts.
- Notebook export to `reports/` with `marimo export html`, registered as an artifact. Nothing consumes reports yet.
- Registry in SQLite instead of TOML. The TOML is readable and hand-edited; sleuth appends to it.
- Unity scene files in the window (FAST_LOOP). Unity has no open-this-scene flag and the EditorPrefs handoff is fragile.
- Tray variant improvements. The README calls the tray optional and not the default.

## Gaps noticed while reading

Each is a place a Tier 1 item would land, not a bug report.

- `catalog.artifacts` sorts by mtime and `latest` returns the last hit. A directory artifact's mtime changes when any child is written, so the newest run folder is not always the newest-started one. #8 fixes the ordering.
- `snippet()` calls `artifacts()` a second time to detect duplicate names, so one snippet costs two full glob passes. #7 removes that.
- `Workbench.show` in Julia converts each artifact's `size` through Python even for the text table. Cheap today; scales with the glob cost above.
- `wb doctor` checks Pluto and IJulia by importing them, which costs a Julia startup every run. A cached result with `--fresh` would make doctor fast enough to run from the window.
- `sleuth --apply` appends a commented block each run, so repeated runs stack duplicate suggestions. A marker line per project would let it replace instead of append.
- The marimo notebook stub inserts the project root into `sys.path` with `parents[1]`, which is right for `<root>/notebooks/` but wrong for a scratch notebook at the root of a project under `notebooks_dir`. `new_notebook` already knows which case it is in.
