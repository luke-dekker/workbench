"""Workbench window: every notebook, grouped by project. Click to open, right-click for everything else.

    wb gui   /   the pinned "Workbench" taskbar button

Contract
- One list: notebooks grouped by project (name, kind, modified). Double-click / Enter opens the
  notebook in the right tool inside that project's env.
- Right-click a project header or any of its notebooks: New marimo / Pluto / Jupyter notebook
  *in that project*, the project's tools (code, terminal, Godot, Unity, ...), open folder, sleuth.
- Filter box at the top. F5 reloads the registry and rescans.
- Needs only the stdlib + tkinter, so the pinned shortcut can run the base pythonw.exe and the
  window shares its taskbar button (see cli.cmd_shortcut).
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import launch as L
from . import registry as R

BG, PANEL, FG, DIM, ACCENT, SEL = "#1c1e24", "#262932", "#e6e6e6", "#8a8f9c", "#4ec9b0", "#3a3f4d"
KIND_LABEL = {"marimo": "marimo", "jupyter": "jupyter", "pluto": "pluto", "octave": "octave", "scene": "godot scene"}
NEW_KINDS = (("marimo", "New marimo notebook"), ("pluto", "New Pluto notebook"), ("jupyter", "New Jupyter notebook"))
APP_ID = "Workbench.Launcher"


class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Workbench")
        self.geometry("900x620")
        self.minsize(640, 400)
        self.configure(bg=BG)
        ico = R.registry_path().parent / "assets" / "workbench.ico"
        if ico.exists():
            try:
                self.iconbitmap(default=str(ico))
            except tk.TclError:
                pass
        self._style()
        self.reg = R.load()
        self.rows: dict[str, tuple[R.Project, object | None]] = {}   # iid -> (project, notebook path or None)
        self._build()
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<F5>", lambda e: self.reload())
        self.after(50, self.reload)

    # ------------------------------------------------------------------ look
    def _style(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL, borderwidth=0)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        s.configure("Dim.TLabel", background=BG, foreground=DIM, font=("Segoe UI", 9))
        s.configure("TEntry", fieldbackground=PANEL, foreground=FG, insertcolor=FG, padding=6)
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=26,
                    font=("Segoe UI", 10))
        s.map("Treeview", background=[("selected", SEL)], foreground=[("selected", FG)])
        s.configure("Treeview.Heading", background=BG, foreground=DIM, font=("Segoe UI", 9), relief="flat")
        s.configure("TButton", background=PANEL, foreground=FG, font=("Segoe UI", 9), padding=(10, 5))
        s.map("TButton", background=[("active", SEL)])

    def _build(self) -> None:
        top = ttk.Frame(self); top.pack(fill="x", padx=12, pady=(10, 6))
        ttk.Label(top, text="Workbench", foreground=ACCENT, font=("Segoe UI Semibold", 13)).pack(side="left")
        self.filter = tk.StringVar()
        self.filter.trace_add("write", lambda *_: self.refresh())
        e = ttk.Entry(top, textvariable=self.filter, width=32)
        e.pack(side="right"); e.focus_set()
        ttk.Label(top, text="filter", style="Dim.TLabel").pack(side="right", padx=(0, 6))

        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=12)
        self.tree = ttk.Treeview(body, columns=("kind", "modified"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="notebook", anchor="w")
        self.tree.heading("kind", text="kind", anchor="w"); self.tree.heading("modified", text="modified", anchor="w")
        self.tree.column("#0", width=520, stretch=True)
        self.tree.column("kind", width=90, stretch=False); self.tree.column("modified", width=150, stretch=False)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.tree.tag_configure("group", foreground=ACCENT, font=("Segoe UI Semibold", 10))
        self.tree.tag_configure("missing", foreground=DIM)
        self.tree.tag_configure("empty", foreground=DIM, font=("Segoe UI", 9, "italic"))
        self.tree.bind("<Double-1>", self.on_activate)
        self.tree.bind("<Return>", self.on_activate)
        self.tree.bind("<Button-3>", self.on_context)
        self.tree.bind("<Shift-F10>", self.on_context)

        foot = ttk.Frame(self); foot.pack(fill="x", padx=12, pady=(6, 10))
        self.status = ttk.Label(foot, text="", style="Dim.TLabel")
        self.status.pack(side="left", fill="x", expand=True)
        ttk.Label(foot, text="double-click opens · right-click for new / tools", style="Dim.TLabel").pack(side="right")

    # ------------------------------------------------------------------ data
    def reload(self) -> None:
        self.reg = R.load()
        self.scan = {name: L.find_notebooks(p) if p.exists else [] for name, p in self.reg.projects.items()}
        self.refresh()
        n = sum(len(v) for v in self.scan.values())
        self.status.config(text=f"{n} notebooks in {len(self.reg.projects)} projects")

    def refresh(self) -> None:
        open_state = {iid: self.tree.item(iid, "open") for iid in self.tree.get_children()}
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        q = self.filter.get().strip().lower()
        for name, p in self.reg.projects.items():
            nbs = self.scan.get(name, [])
            if q:
                nbs = [(path, kind) for path, kind in nbs
                       if q in path.relative_to(p.root).as_posix().lower() or q in name.lower() or q in kind]
                if not nbs and q not in name.lower():
                    continue
            label = f"{name}   ·   {len(nbs)}" if p.exists else f"{name}   (folder missing)"
            gid = self.tree.insert("", "end", iid=f"g:{name}", text=label, open=open_state.get(f"g:{name}", True),
                                   tags=("group",) if p.exists else ("group", "missing"))
            self.rows[gid] = (p, None)
            if p.exists and not nbs:
                eid = self.tree.insert(gid, "end", text="no notebooks yet — right-click to create one", tags=("empty",))
                self.rows[eid] = (p, None)
            for path, kind in nbs:
                rel = path.relative_to(p.root).as_posix()
                mod = __import__("datetime").datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                iid = self.tree.insert(gid, "end", text=rel, values=(KIND_LABEL.get(kind, kind), mod))
                self.rows[iid] = (p, path)

    # --------------------------------------------------------------- actions
    def _at(self, event=None):
        iid = self.tree.identify_row(event.y) if event is not None and hasattr(event, "y") else None
        iid = iid or (self.tree.selection()[0] if self.tree.selection() else None)
        return iid, self.rows.get(iid, (None, None))

    def on_activate(self, event=None) -> None:
        iid, (p, path) = self._at(event if event and event.type == tk.EventType.ButtonPress else None)
        if p is None:
            return
        if path is None:   # header: toggle
            self.tree.item(iid, open=not self.tree.item(iid, "open"))
            return
        if path.suffix.lower() == ".tscn":
            self.run(lambda: L.open_notebook(p, self.reg, path), f"running {path.name} in Godot (no editor)")
            return
        self.run(lambda: L.open_notebook(p, self.reg, path),
                 f"starting {path.name} in {p.name}: a browser tab will open (first run per project can take a minute)")

    def on_context(self, event) -> None:
        iid, (p, path) = self._at(event)
        if p is None:
            return
        self.tree.selection_set(iid)
        m = tk.Menu(self, tearoff=0, bg=PANEL, fg=FG, activebackground=SEL, activeforeground=FG, bd=0)
        if path is not None:
            m.add_command(label=f"Open {path.name}", command=lambda: self.run(
                lambda: L.open_notebook(p, self.reg, path), f"opening {path.name}"))
            m.add_command(label="Show in folder", command=lambda: self.run(lambda: _reveal(path), "explorer"))
            m.add_command(label="Copy path", command=lambda: self._copy(str(path)))
            m.add_separator()
        if p.exists:
            for kind, label in NEW_KINDS:
                m.add_command(label=f"{label} in {p.name}", command=lambda k=kind: self.new_in(p, k))
            m.add_separator()
            for t in p.tools:
                m.add_command(label=t, command=lambda t=t: self.run(lambda: L.launch(p, self.reg, t), f"{p.name}: {t}"))
            m.add_command(label="open folder", command=lambda: self.run(lambda: _reveal(p.root), "explorer"))
            m.add_separator()
            m.add_command(label="sleuth outputs", command=lambda: self.sleuth(p))
        else:
            m.add_command(label=f"Create folder {p.root}", command=lambda: self.run(lambda: self.create(p), "created"))
        m.add_separator()
        running = L.running_servers()
        m.add_command(label=f"Stop notebook servers ({len(running)})", state="normal" if running else "disabled",
                      command=lambda: self.status.config(text=f"stopped {L.stop_servers()} server(s)"))
        m.add_command(label="Open server logs folder", command=lambda: self.run(
            lambda: (L.LOG_DIR.mkdir(exist_ok=True), _reveal(L.LOG_DIR)), "logs"))
        m.add_command(label="Edit registry", command=lambda: self.run(
            lambda: L.code(self.reg.projects["workbench"], self.reg, [str(self.reg.path)]) if "workbench" in self.reg.projects
            else L._spawn(["cmd", "/c", "code", str(self.reg.path)]), "registry"))
        m.add_command(label="Reload (F5)", command=self.reload)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def new_in(self, p: R.Project, kind: str) -> None:
        name = simpledialog.askstring("New notebook", f"{kind} notebook in {p.name}\nname:", parent=self)
        if name is None:
            return
        self.run(lambda: L.new_notebook(p, self.reg, kind, name or ""), f"created {kind} notebook in {p.name}")
        self.reload()

    def create(self, p: R.Project) -> list[str]:
        p.root.mkdir(parents=True, exist_ok=True)
        self.reload()
        return ["mkdir", str(p.root)]

    def sleuth(self, p: R.Project) -> None:
        from . import sleuth as S
        self.status.config(text=f"sleuthing {p.name} ..."); self.update_idletasks()
        try:
            text = S.format_report(S.sleuth(p, self.reg))
        except Exception as e:
            messagebox.showerror("Workbench", str(e), parent=self); return
        win = tk.Toplevel(self); win.title(f"sleuth: {p.name}"); win.geometry("900x600"); win.configure(bg=BG)
        box = tk.Text(win, bg=PANEL, fg=FG, insertbackground=FG, font=("Cascadia Mono", 10), wrap="none")
        box.insert("1.0", text); box.configure(state="disabled"); box.pack(fill="both", expand=True, padx=8, pady=8)
        self.status.config(text=f"sleuth report for {p.name} open")

    def _copy(self, text: str) -> None:
        self.clipboard_clear(); self.clipboard_append(text); self.status.config(text="path copied")

    def run(self, fn, what: str = "") -> None:
        try:
            fn()
            self.status.config(text=what or "launched")
        except Exception as e:
            self.status.config(text=f"error: {e}")
            messagebox.showerror("Workbench", str(e), parent=self)


def _reveal(path) -> list[str]:
    """Open a folder (or select a file) in Explorer. os.startfile avoids the forward-slash fallback bug."""
    p = os.fspath(path)
    if os.path.isdir(p):
        os.startfile(p)
    else:
        L._spawn(["explorer", "/select,", os.path.normpath(p)])
    return ["explorer", p]


def main() -> int:
    marker = R.registry_path().parent / "assets" / ".aumid"
    if sys.platform == "win32" and marker.exists():
        # `wb shortcut` wrote the same id into the .lnk -> one taskbar button, not two.
        # Without the marker the shortcut has no explicit id, so we must not set one either.
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(marker.read_text().strip() or APP_ID)
        except Exception:
            pass
    Launcher().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
