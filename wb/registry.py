"""Load and query workbench.toml."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REGISTRY_ENV = "WORKBENCH_TOML"
DEFAULT_REGISTRY = Path(__file__).resolve().parent.parent / "workbench.toml"


@dataclass
class Project:
    name: str
    root: Path
    kind: str
    tags: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    commands: dict[str, str] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    def expand(self, s: str) -> str:
        return s.replace("{root}", str(self.root))

    @property
    def godot_dir(self) -> Path | None:
        g = self.extra.get("godot_dir")
        return Path(self.expand(g)) if g else None

    @property
    def exists(self) -> bool:
        return self.root.exists()


@dataclass
class Registry:
    path: Path
    apps: dict[str, str]
    defaults: dict
    projects: dict[str, Project]

    def project(self, name: str) -> Project:
        if name in self.projects:
            return self.projects[name]
        # prefix match as a convenience: `wb open node web`
        hits = [p for p in self.projects if p.startswith(name)]
        if len(hits) == 1:
            return self.projects[hits[0]]
        raise KeyError(f"unknown project {name!r} (known: {', '.join(self.projects)})")


def registry_path() -> Path:
    return Path(os.environ.get(REGISTRY_ENV, DEFAULT_REGISTRY))


def load(path: Path | None = None) -> Registry:
    path = path or registry_path()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    projects: dict[str, Project] = {}
    for name, cfg in data.get("projects", {}).items():
        cfg = dict(cfg)
        projects[name] = Project(
            name=name,
            root=Path(cfg.pop("root")),
            kind=cfg.pop("kind", "python"),
            tags=cfg.pop("tags", []),
            tools=cfg.pop("tools", []),
            commands=cfg.pop("commands", {}),
            extra=cfg,
        )
    return Registry(
        path=path,
        apps=data.get("apps", {}),
        defaults=data.get("defaults", {}),
        projects=projects,
    )
