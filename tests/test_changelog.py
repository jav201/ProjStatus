from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.services.storage import StorageService


def _storage(tmp_path: Path) -> StorageService:
    return StorageService(AppConfig.from_root(tmp_path))


def test_changelog_appended_with_actor_and_summary(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    project = storage.create_project("Alpha")
    storage.save_project(
        project,
        sections={"content": "scope", "change_requests": "", "roadblocks": "", "notes": ""},
        note="Initial scope",
        actor="alice",
    )

    log = (tmp_path / "projects" / project.slug / "CHANGELOG.md").read_text()
    lines = [line for line in log.splitlines() if line.strip()]
    assert len(lines) >= 2  # one for create_project (web), one for our explicit save
    last = lines[-1]
    assert "alice" in last
    assert "Initial scope" in last


def test_changelog_grows_per_save(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    project = storage.create_project("Beta")
    sections = {"content": "v1", "change_requests": "", "roadblocks": "", "notes": ""}

    for actor, content in [("bob", "v2"), ("bob", "v3"), ("maria", "v4")]:
        sections["content"] = content
        storage.save_project(project, sections, actor=actor)

    log = (tmp_path / "projects" / project.slug / "CHANGELOG.md").read_text()
    lines = [line for line in log.splitlines() if line.strip()]
    # 1 create + 3 updates = 4 lines
    assert len(lines) == 4
    assert "bob" in lines[1]
    assert "bob" in lines[2]
    assert "maria" in lines[3]


def test_addendum_carries_configured_actor(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    project = storage.create_project("Gamma")
    addendum = storage.save_project(
        project,
        sections={"content": "", "change_requests": "", "roadblocks": "", "notes": ""},
        actor="diego",
    )
    assert addendum.actor == "diego"


def test_default_actor_falls_back_to_web(tmp_path: Path) -> None:
    """Backwards-compat: callers that don't pass actor= still get the legacy 'web' tag."""
    storage = _storage(tmp_path)
    project = storage.create_project("Delta")
    addendum = storage.save_project(
        project,
        sections={"content": "", "change_requests": "", "roadblocks": "", "notes": ""},
    )
    assert addendum.actor == "web"
