from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    root_dir: Path
    projects_dir: Path
    exports_dir: Path
    project_templates_dir: Path
    document_templates_dir: Path
    static_dir: Path
    templates_dir: Path
    default_board_columns: tuple[str, ...] = ("Backlog", "In Progress", "Blocked", "Done")
    default_access_categories: tuple[str, ...] = (
        "Shared Folders",
        "Docs",
        "Meetings",
        "Tools",
    )

    @classmethod
    def from_root(cls, root_dir: Path) -> "AppConfig":
        root_dir = root_dir.resolve()
        return cls(
            root_dir=root_dir,
            projects_dir=root_dir / "projects",
            exports_dir=root_dir / "exports",
            project_templates_dir=root_dir / "project_templates",
            document_templates_dir=root_dir / "document_templates",
            static_dir=root_dir / "app" / "static",
            templates_dir=root_dir / "app" / "templates",
        )
