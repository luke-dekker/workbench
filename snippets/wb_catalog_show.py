import marimo

__generated_with = "0.25.0"
app = marimo.App()

@app.cell
def _(mo):
    mo.md(r"""
    # Workbench: what data do I have?

    List every artifact the workbench registry knows about (fieldrec sessions, node-tool exports, sceneforge runs). Nothing is loaded.
    """)
    return

@app.cell
def _():
    from wb import catalog
    catalog.show()                 # all projects
    # catalog.show("fieldrec")     # one project
    # catalog.artifacts("node-tool", kind="safetensors")
    return


if __name__ == "__main__":
    app.run()
