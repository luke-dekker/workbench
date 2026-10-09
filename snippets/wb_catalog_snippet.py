import marimo

__generated_with = "0.25.0"
app = marimo.App()

@app.cell
def _(mo):
    mo.md(r"""
    # Workbench: get the loader code for an artifact

    Pick an artifact, print the code that loads it, paste it into a cell.
    """)
    return

@app.cell
def _():
    from wb import catalog
    art = catalog.find("august_farm", "sceneforge")
    print(catalog.snippet(art))
    return


if __name__ == "__main__":
    app.run()
