import marimo

__generated_with = "0.25.0"
app = marimo.App()

@app.cell
def _(mo):
    mo.md(r"""
    # Workbench: Arrow table to polars / pandas

    The catalog hands back pyarrow tables; convert once and work in your preferred frame library.
    """)
    return

@app.cell
def _():
    import polars as pl
    # df = pl.from_arrow(sess[topic])       # polars
    # df = sess[topic].to_pandas()          # pandas
    return


if __name__ == "__main__":
    app.run()
