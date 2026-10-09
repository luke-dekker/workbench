import marimo

__generated_with = "0.25.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    from pathlib import Path
    import numpy as np
    import pyarrow.parquet as pq
    from safetensors.numpy import load_file

    DATA = Path(__file__).parent / "data"
    return DATA, load_file, mo, np, pq


@app.cell
def _(DATA, load_file, pq):
    tensors = load_file(DATA / "tensors.safetensors")
    table = pq.read_table(DATA / "table.parquet")
    return table, tensors


@app.cell
def _(mo, np, table, tensors):
    rows = [
        {"name": k, "dtype": str(v.dtype), "shape": str(v.shape), "mean": round(float(np.mean(v)), 4)}
        for k, v in tensors.items()
    ]
    agree = np.isclose(table.column("signal").to_numpy().mean(), tensors["signal"].mean())
    print(f"marimo: {len(rows)} tensors, table rows={table.num_rows}, signal means agree={agree}")
    mo.vstack([
        mo.md("# Interop proof: one dataset, every runtime"),
        mo.md(f"safetensors tensors + parquet table from `{table.num_rows}` rows. Means agree: **{agree}**"),
        mo.ui.table(rows),
    ])
    return


if __name__ == "__main__":
    app.run()
