from __future__ import annotations

from copy import deepcopy
from datetime import date

from app.models import (
    Milestone,
    MilestoneStatus,
    Priority,
    Project,
    Task,
)
from app.services.mermaid import ISO_WEEK_AXIS_TOKEN, import_timeline, render_timeline


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


def _axis_format_line(text: str) -> str:
    for raw in text.splitlines():
        if raw.strip().startswith("axisFormat "):
            return raw
    raise AssertionError("axisFormat line not found in rendered Mermaid source")


# TC-009 — HLR-009 behavioural: axisFormat line contains the week token
def test_tc_009_render_timeline_axis_contains_week_token() -> None:
    text = render_timeline(_project_with_one_each())
    axis_line = _axis_format_line(text)
    assert ISO_WEEK_AXIS_TOKEN in axis_line


# TC-014 — HLR-014 behavioural: literal `W` in axisFormat, round-trip ok=True,
# conditional `%V` absence (only when fallback chosen).
def test_tc_014_axis_has_w_and_roundtrip_ok() -> None:
    project = _project_with_one_each()
    text = render_timeline(project)
    axis_line = _axis_format_line(text)
    assert "W" in axis_line
    fresh = _project_with_one_each()
    _, _imported_msgs, _errors, ok = import_timeline(fresh, text)
    assert ok is True
    if ISO_WEEK_AXIS_TOKEN != "%V":
        assert "%V" not in axis_line


# TC-029 — LLR-009.1: literal `W` appears ONLY on the axisFormat line.
def test_tc_029_w_only_on_axis_format_line() -> None:
    text = render_timeline(_project_with_one_each())
    axis_line = _axis_format_line(text)
    for raw in text.splitlines():
        if raw is axis_line or raw.strip().startswith("axisFormat "):
            continue
        assert "W" not in raw, f"unexpected W on non-axis line: {raw!r}"


# TC-030 — LLR-009.2 (per CR-002 deepcopy fix, CR-004 list naming): round-trip
# is byte-identical when the input is a deep-copied project model.
def test_tc_030_roundtrip_byte_identical_via_deepcopy() -> None:
    original = _project_with_one_each()
    rendered_before = render_timeline(original)
    imported, _imported_msgs, _errors, ok = import_timeline(deepcopy(original), rendered_before)
    assert ok is True
    assert render_timeline(imported) == rendered_before


# TC-038 — LLR-014.1: same shape as TC-014 plus a redundancy check on the
# axis-line `Wnn`-source presence (W is in the axis-format directive).
def test_tc_038_fallback_token_assertion_is_conditional() -> None:
    text = render_timeline(_project_with_one_each())
    axis_line = _axis_format_line(text)
    assert "W" in axis_line
    fresh = _project_with_one_each()
    _, _imported_msgs, _errors, ok = import_timeline(fresh, text)
    assert ok is True
    if ISO_WEEK_AXIS_TOKEN != "%V":
        assert "%V" not in axis_line
