from __future__ import annotations

from datetime import date

from app.models import (
    Milestone,
    MilestoneStatus,
    Priority,
    Project,
    Task,
)
from app.services.mermaid import import_timeline, render_timeline


def _project_with_one_each() -> Project:
    project = Project(slug="p", name="P", board_columns=["Backlog", "In Progress", "Blocked", "Done"])
    project.milestones = [
        Milestone(id="milestone_aaa", title="Spec frozen", target_date=date(2026, 4, 21), status=MilestoneStatus.COMPLETE),
        Milestone(id="milestone_bbb", title="Award", target_date=date(2026, 6, 1), status=MilestoneStatus.BLOCKED),
    ]
    project.tasks = [
        Task(id="task_aaa", title="Run risk scoring", column="In Progress", start_date=date(2026, 4, 26), due_date=date(2026, 4, 26), priority=Priority.HIGH),
        Task(id="task_bbb", title="Negotiate NDA", column="Blocked", start_date=date(2026, 4, 26), due_date=date(2026, 4, 26)),
        Task(id="task_ccc", title="Compile longlist", column="Done", start_date=date(2026, 4, 26), due_date=date(2026, 4, 26)),
    ]
    return project


def test_render_timeline_has_no_debug_markers_in_labels() -> None:
    text = render_timeline(_project_with_one_each())
    # no [task| or [milestone| anywhere — those would leak into rendered Gantt labels
    assert "[task|" not in text
    assert "[milestone|" not in text
    # task title must appear cleanly with no surrounding brackets
    assert "Run risk scoring :" in text
    assert "Spec frozen :milestone" in text


def test_render_timeline_emits_today_marker() -> None:
    text = render_timeline(_project_with_one_each())
    assert "todayMarker" in text


def test_render_timeline_round_trip_preserves_titles_and_dates() -> None:
    project = _project_with_one_each()
    text = render_timeline(project)
    fresh = _project_with_one_each()
    imported, summary, errors, supported = import_timeline(fresh, text)
    assert supported, f"errors: {errors}"
    assert imported.milestones[0].title == "Spec frozen"
    assert imported.milestones[0].status == MilestoneStatus.COMPLETE
    assert imported.milestones[1].status == MilestoneStatus.BLOCKED
    assert imported.tasks[0].title == "Run risk scoring"


def test_legacy_format_still_imports() -> None:
    project = _project_with_one_each()
    legacy = (
        "gantt\n"
        "  title P\n"
        "  dateFormat YYYY-MM-DD\n"
        "  axisFormat %b %d\n"
        "  section Milestones\n"
        f"  Renamed spec [milestone|{project.milestones[0].id}]: milestone, complete, 2026-04-21, 0d\n"
        "  section In Progress\n"
        f"  Renamed risk [task|{project.tasks[0].id}]: active, 2026-04-26, 1d\n"
    )
    fresh = _project_with_one_each()
    imported, summary, errors, supported = import_timeline(fresh, legacy)
    assert supported, f"errors: {errors}"
    assert imported.milestones[0].title == "Renamed spec"
    assert imported.tasks[0].title == "Renamed risk"


def test_unsupported_lines_surface_errors() -> None:
    project = _project_with_one_each()
    text = (
        "gantt\n"
        "  title P\n"
        "  dateFormat YYYY-MM-DD\n"
        "  some random line that doesn't fit\n"
    )
    _, _, errors, supported = import_timeline(project, text)
    assert not supported
    assert any("some random line" in e for e in errors)
