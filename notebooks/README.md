# notebooks

Scratch notebooks that are not tied to a project. Project-specific notebooks live in the project.

All of these show up under the **workbench** project in the window; right-click it to add more.

- `marimo/`  — marimo scratch notebooks
- `julia/`   — Pluto scratch notebooks
- `octave/`  — `.m` scripts (open in the Octave GUI)
- `interop/` — the shared-format proof: one data file, read from every runtime

## Formats (the contract)

| data kind | format      | writers / readers already in the fleet            |
|-----------|-------------|---------------------------------------------------|
| tensors   | safetensors | node-tool export, torch, numpy, Julia (via PythonCall) |
| tables    | Arrow/Parquet | pandas/polars, marimo, Julia Arrow.jl, Octave (via Python) |
| scenes    | glTF        | Godot, Unity, Blender, sceneforge                 |
| logs      | MCAP        | fieldrec, Foxglove-compatible readers             |
| live      | WebSocket + JSON | node-tool server, Godot frontend             |
