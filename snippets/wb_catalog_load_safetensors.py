import marimo

__generated_with = "0.25.0"
app = marimo.App()

@app.cell
def _(mo):
    mo.md(r"""
    # Workbench: load a safetensors export

    node-tool exports (or the interop sample) as {name: numpy array}. Pass framework='torch' for tensors.
    """)
    return

@app.cell
def _():
    from wb import catalog
    art = catalog.latest("workbench", kind="safetensors")   # or "node-tool"
    tensors = catalog.load(art)
    {k: v.shape for k, v in tensors.items()}
    return


if __name__ == "__main__":
    app.run()
