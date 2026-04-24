from __future__ import annotations

import difflib
from datetime import datetime

from app.models import Addendum, ProjectSnapshot
from app.utils import dumps_pretty


def snapshot_diff(before: ProjectSnapshot | None, after: ProjectSnapshot) -> tuple[list[str], dict[str, str]]:
    changed_files: list[str] = []
    diffs: dict[str, str] = {}

    before_json = dumps_pretty(before.project.model_dump(mode="json")) if before else ""
    after_json = dumps_pretty(after.project.model_dump(mode="json"))
    if before_json != after_json:
        changed_files.append("project.json")
        diffs["project.json"] = _diff_text("project.json", before_json, after_json)

    for section_name, section_text in after.sections.items():
        previous = before.sections.get(section_name, "") if before else ""
        if previous != section_text:
            filename = f"{section_name}.md"
            changed_files.append(filename)
            diffs[filename] = _diff_text(filename, previous, section_text)

    before_timeline = before.timeline_text if before else ""
    if before_timeline != after.timeline_text:
        changed_files.append("timeline.mmd")
        diffs["timeline.mmd"] = _diff_text("timeline.mmd", before_timeline, after.timeline_text)

    return changed_files, diffs


def build_addendum(
    entry_id: str,
    created_at: datetime,
    note: str,
    actor: str,
    before: ProjectSnapshot | None,
    after: ProjectSnapshot,
) -> Addendum:
    changed_files, diffs = snapshot_diff(before, after)
    summary = [
        f"Saved {after.project.name}",
        f"{len(after.project.tasks)} tasks across {len(after.project.board_columns)} columns",
        f"{len(after.project.milestones)} milestones and {len(after.project.people)} people",
    ]
    if note:
        summary.append(f"Note: {note}")
    return Addendum(
        id=entry_id,
        created_at=created_at,
        note=note,
        actor=actor,
        changed_files=changed_files,
        summary=summary,
        diffs=diffs,
        snapshot=after,
    )


def render_addendum_markdown(addendum: Addendum) -> str:
    lines = [
        f"# Addendum {addendum.id}",
        "",
        f"- Created at: {addendum.created_at.isoformat()}",
        f"- Actor: {addendum.actor}",
        "",
        "## Summary",
        "",
    ]
    lines.extend(f"- {item}" for item in addendum.summary)
    if addendum.note:
        lines.extend(["", "## Note", "", addendum.note])
    if addendum.changed_files:
        lines.extend(["", "## Changed Files", ""])
        lines.extend(f"- {path}" for path in addendum.changed_files)
    for filename, diff_text in addendum.diffs.items():
        lines.extend(["", f"## {filename}", "", "```diff", diff_text.rstrip("\n"), "```"])
    return "\n".join(lines) + "\n"


def _diff_text(filename: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )
