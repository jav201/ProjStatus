from __future__ import annotations

import json
from pathlib import Path

from app.config import AppConfig
from app.models import Milestone, Task
from app.services.storage import StorageService


def make_storage(tmp_path: Path) -> StorageService:
    return StorageService(AppConfig.from_root(tmp_path))


def test_create_project_writes_expected_files(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)

    project = storage.create_project("Alpha Launch", description="Ship the new portal")

    project_dir = tmp_path / "projects" / project.slug
    assert (project_dir / "project.json").exists()
    assert (project_dir / "timeline.mmd").exists()
    for section in ("content", "change_requests", "roadblocks", "notes"):
        assert (project_dir / f"{section}.md").exists()
    history_files = list((project_dir / "history").glob("*.json"))
    assert history_files


def test_external_markdown_and_timeline_changes_are_imported(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    project = storage.create_project("Beta Timeline")
    loaded = storage.load_project(project.slug)

    if not loaded.project.milestones:
        loaded.project.milestones.append(Milestone(title="Kickoff", target_date="2026-04-30"))
    loaded.project.tasks.append(
        Task(
            title="Build API",
            column="In Progress",
            start_date="2026-04-24",
            due_date="2026-04-26",
        )
    )
    storage.save_project(loaded.project, loaded.sections, note="Seed timeline")

    project_dir = tmp_path / "projects" / project.slug
    (project_dir / "content.md").write_text("# Updated content\n\nNew detail.", encoding="utf-8")
    timeline_text = (
        "gantt\n"
        "  title Beta Timeline\n"
        "  dateFormat YYYY-MM-DD\n"
        "  axisFormat %b %d\n"
        "  section Tasks\n"
        f"  Build API revised [task|{loaded.project.tasks[0].id}]: active, 2026-04-25, 4d\n"
    )
    (project_dir / "timeline.mmd").write_text(timeline_text, encoding="utf-8")

    refreshed = storage.load_project(project.slug)

    assert "content.md changed outside the app" in refreshed.sync_notice
    assert "timeline.mmd changed outside the app" in refreshed.sync_notice
    assert refreshed.sections["content"].startswith("# Updated content")
    assert refreshed.project.tasks[0].title == "Build API revised"
    assert refreshed.project.tasks[0].start_date.isoformat() == "2026-04-25"
    assert refreshed.project.tasks[0].due_date.isoformat() == "2026-04-28"


def test_invalid_project_json_falls_back_to_latest_snapshot(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    project = storage.create_project("Gamma Restore")
    project_dir = tmp_path / "projects" / project.slug
    (project_dir / "project.json").write_text("{ invalid json", encoding="utf-8")

    loaded = storage.load_project(project.slug)

    assert loaded.project.name == "Gamma Restore"
    assert loaded.validation_errors
    assert "Invalid project.json detected." in loaded.validation_errors[0]


def test_restore_history_creates_new_addendum(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    project = storage.create_project("Delta History")
    loaded = storage.load_project(project.slug)
    loaded.sections["notes"] = "Before restore"
    storage.save_project(loaded.project, loaded.sections, note="Updated notes")

    addendums = storage.load_project(project.slug).addendums
    original_count = len(addendums)
    target_id = addendums[-1].id

    storage.restore_history(project.slug, target_id, note="Rollback")
    restored = storage.load_project(project.slug)

    assert len(restored.addendums) == original_count + 1
    assert restored.addendums[0].note == "Rollback"
