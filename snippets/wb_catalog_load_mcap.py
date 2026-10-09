import marimo

__generated_with = "0.25.0"
app = marimo.App()

@app.cell
def _(mo):
    mo.md(r"""
    # Workbench: load a fieldrec MCAP session

    Newest session as a dict of topic -> pyarrow.Table. Use `catalog.find('name')` for a specific one.
    """)
    return

@app.cell
def _():
    from wb import catalog
    sess = catalog.load(catalog.latest("fieldrec", kind="mcap", group="sessions"))
    list(sess)                      # topics
    return

@app.cell
def _():
    topic = list(sess)[0]
    sess[topic].to_pandas().head()
    return


if __name__ == "__main__":
    app.run()
