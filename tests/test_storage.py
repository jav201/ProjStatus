from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.config import AppConfig
from app.models import DocumentTemplateField, Milestone, Person, Task
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


def test_archive_duplicate_delete_and_dashboard_search_sort(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    first = storage.create_project("Alpha Atlas", description="Migration control", end_date=date(2026, 5, 15))
    second = storage.create_project("Beta Beacon", description="Service rollout", end_date=date(2026, 6, 1))

    first_loaded = storage.load_project(first.slug)
    first_loaded.project.people.append(Person(name="Alex Roe", email="alex@example.com", role="Project Manager"))
    first_loaded.project.logo_path = "assets/logo.png"
    first_loaded.project.milestones.append(Milestone(title="Kickoff", target_date=date(2026, 4, 28)))
    first_logo = tmp_path / "projects" / first.slug / "assets" / "logo.png"
    first_logo.parent.mkdir(parents=True, exist_ok=True)
    first_logo.write_bytes(b"fake-png")
    storage.save_project(first_loaded.project, first_loaded.sections, note="Seed alpha")

    second_loaded = storage.load_project(second.slug)
    second_loaded.project.people.append(Person(name="Morgan Lee", email="morgan@example.com", role="Sponsor"))
    second_loaded.project.milestones.append(Milestone(title="Review", target_date=date(2026, 5, 20)))
    storage.save_project(second_loaded.project, second_loaded.sections, note="Seed beta")

    by_name = storage.list_dashboard_projects(sort_by="name", include_archived=True)
    assert [item.slug for item in by_name] == [first.slug, second.slug]

    by_milestone = storage.list_dashboard_projects(sort_by="next_milestone", include_archived=True)
    assert [item.slug for item in by_milestone] == [first.slug, second.slug]

    stakeholder_search = storage.list_dashboard_projects(search="alex@example.com", include_archived=True)
    assert [item.slug for item in stakeholder_search] == [first.slug]

    storage.archive_project(first.slug)
    active_only = storage.list_dashboard_projects()
    assert [item.slug for item in active_only] == [second.slug]

    archived_visible = storage.list_dashboard_projects(include_archived=True)
    archived_entry = next(item for item in archived_visible if item.slug == first.slug)
    assert archived_entry.archived is True
    assert archived_entry.has_logo is True

    duplicate = storage.duplicate_project(first.slug, "Alpha Atlas Copy")
    duplicate_dir = tmp_path / "projects" / duplicate.slug
    assert duplicate_dir.exists()
    assert (duplicate_dir / "assets" / "logo.png").exists()
    assert len(list((duplicate_dir / "history").glob("*.json"))) == 1

    storage.unarchive_project(first.slug)
    restored_entry = next(item for item in storage.list_dashboard_projects(include_archived=True) if item.slug == first.slug)
    assert restored_entry.archived is False

    storage.delete_project(duplicate.slug)
    assert not duplicate_dir.exists()


def test_project_and_document_templates(tmp_path: Path) -> None:
    storage = make_storage(tmp_path)
    source = storage.create_project("Source Project", description="Seed")
    loaded = storage.load_project(source.slug)
    loaded.project.milestones.append(Milestone(title="Gate Review", target_date=date(2026, 5, 1)))
    loaded.sections["content"] = "Starter scope"
    storage.save_project(loaded.project, loaded.sections, note="Seed template content")

    template = storage.create_project_template_from_project(source.slug, "Gate Template", "Reusable gate flow")
    assert template.slug == "gate-template"
    assert (tmp_path / "project_templates" / "gate-template.json").exists()

    created = storage.create_project_from_template("gate-template", "New Gate Project")
    refreshed = storage.load_project(created.slug)
    assert refreshed.project.name == "New Gate Project"
    assert refreshed.project.milestones[0].title == "Gate Review"
    assert refreshed.sections["content"] == "Starter scope"

    document = storage.create_document_template(
        "RFQ Packet",
        "Supplier request",
        [
            DocumentTemplateField(key="part_number", label="Part Number", aliases="PN,Item Number", value=""),
            DocumentTemplateField(key="bom_table", label="BOM Table", field_type="excel_table", value="Rows ready"),
        ],
    )
    assert document.completion_percent == 50
    assert document.missing_fields[0].key == "part_number"
    assert storage.list_document_templates()[0].fields[0].aliases == ["PN", "Item Number"]


def test_section_round_trip_does_not_grow_newlines(tmp_path: Path) -> None:
    """Regression: saving a section with CRLF line endings should not double newlines.

    Before the fix, Path.write_text on Windows translated \\n to \\r\\n while leaving
    existing \\r alone. Each round trip then grew runs of newlines exponentially.
    """
    storage = make_storage(tmp_path)
    project = storage.create_project("Newline Project")
    crlf_body = "first paragraph\r\n\r\nsecond paragraph\r\n"

    loaded = storage.load_project(project.slug)
    loaded.sections["notes"] = crlf_body.replace("\r\n", "\n").replace("\r", "\n")
    storage.save_project(loaded.project, loaded.sections, note="first save")

    # save 4 more times to exercise the exponential-growth path
    for _ in range(4):
        loaded = storage.load_project(project.slug)
        storage.save_project(loaded.project, loaded.sections, note="re-save")

    final = storage.load_project(project.slug).sections["notes"]
    # exactly one blank line between paragraphs, no growth
    assert "\r" not in final
    assert "\n\n\n" not in final
    assert final.count("\n\n") == 1


def test_dictionary_overrides_template_field_values(tmp_path: Path) -> None:
    """build_render_context should let project.dictionary override template default values."""
    from app.models import DictionaryEntry, DocumentTemplate, Project
    from app.services.storage import build_render_context

    project = Project(slug="p", name="Demo")
    project.dictionary = [
        DictionaryEntry(key="part_number", value="ABC-12345"),
        DictionaryEntry(key="supplier_name", value="Acme Corp"),
    ]
    template = DocumentTemplate(
        slug="t",
        name="Quote",
        fields=[
            DocumentTemplateField(key="part_number", label="Part", value="DEFAULT-XXX"),
            DocumentTemplateField(key="supplier_name", label="Supplier", value=""),
            DocumentTemplateField(key="revision", label="Rev", value="A"),
        ],
    )
    ctx = build_render_context(template, project)
    assert ctx["part_number"] == "ABC-12345"  # dictionary wins
    assert ctx["supplier_name"] == "Acme Corp"  # dictionary fills empty default
    assert ctx["revision"] == "A"  # untouched template value


def test_load_project_heals_existing_corruption(tmp_path: Path) -> None:
    """If a section file already has 4+ consecutive newlines on disk,
    load_project should collapse them down to 2 paragraph breaks."""
    storage = make_storage(tmp_path)
    project = storage.create_project("Heal Project")

    # write corrupted notes directly (simulating damage from prior bug)
    (tmp_path / "projects" / project.slug / "notes.md").write_text(
        "intro\n\n\n\n\n\nbody\n", encoding="utf-8", newline="\n"
    )
    loaded = storage.load_project(project.slug)
    assert loaded.sections["notes"] == "intro\n\nbody\n"
