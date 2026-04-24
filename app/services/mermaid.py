from __future__ import annotations

import re
from datetime import date

from app.models import MilestoneStatus, Project
from app.utils import date_to_duration_days, due_from_duration


TASK_LINE_RE = re.compile(
    r"^(?P<title>.+?) \[task\|(?P<id>[\w\-]+)\]: (?:(?P<status>[A-Za-z,\s]+), )?(?P<start>\d{4}-\d{2}-\d{2}), (?P<duration>\d+)d$"
)
MILESTONE_LINE_RE = re.compile(
    r"^(?P<title>.+?) \[milestone\|(?P<id>[\w\-]+)\]: milestone(?:, (?P<status>\w+))?, (?P<date>\d{4}-\d{2}-\d{2}), 0d$"
)


def render_timeline(project: Project) -> str:
    lines = [
        "gantt",
        f"  title {project.name}",
        "  dateFormat YYYY-MM-DD",
        "  axisFormat %b %d",
        "  section Milestones",
    ]
    for milestone in project.milestones:
        if not milestone.target_date:
            continue
        status_suffix = f", {milestone.status.value}" if milestone.status != MilestoneStatus.PLANNED else ""
        lines.append(
            f"  {milestone.title} [milestone|{milestone.id}]: milestone{status_suffix}, {milestone.target_date.isoformat()}, 0d"
        )
    task_order = {column: [] for column in project.board_columns}
    for task in project.tasks:
        task_order.setdefault(task.column, []).append(task)

    for column in project.board_columns:
        if not task_order.get(column):
            continue
        lines.append(f"  section {column}")
        for task in task_order[column]:
            start = task.start_date.isoformat() if task.start_date else date.today().isoformat()
            duration = date_to_duration_days(task.start_date, task.due_date)
            status_tokens: list[str] = []
            if task.column == "Done":
                status_tokens.append("done")
            elif task.column == "In Progress":
                status_tokens.append("active")
            if task.blocked or task.column == "Blocked":
                status_tokens.append("crit")
            status_prefix = f"{', '.join(status_tokens)}, " if status_tokens else ""
            lines.append(f"  {task.title} [task|{task.id}]: {status_prefix}{start}, {duration}d")
    return "\n".join(lines) + "\n"


def import_timeline(project: Project, timeline_text: str) -> tuple[Project, list[str], list[str], bool]:
    imported: list[str] = []
    errors: list[str] = []
    task_positions: list[str] = []
    supported = True
    current_section = ""
    milestone_map = {milestone.id: milestone for milestone in project.milestones}
    task_map = {task.id: task for task in project.tasks}

    for raw_line in timeline_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("section "):
            current_section = line.replace("section ", "", 1).strip()
            continue
        if line.startswith("%%"):
            continue
        milestone_match = MILESTONE_LINE_RE.match(line)
        if milestone_match:
            milestone_id = milestone_match.group("id")
            milestone = milestone_map.get(milestone_id)
            if milestone is None:
                supported = False
                continue
            milestone.title = milestone_match.group("title")
            milestone.target_date = date.fromisoformat(milestone_match.group("date"))
            status_value = milestone_match.group("status") or MilestoneStatus.PLANNED.value
            milestone.status = MilestoneStatus(status_value)
            imported.append(f"Updated milestone '{milestone.title}' from timeline")
            continue
        task_match = TASK_LINE_RE.match(line)
        if task_match:
            task_id = task_match.group("id")
            task = task_map.get(task_id)
            if task is None:
                supported = False
                continue
            task.title = task_match.group("title")
            task.start_date = date.fromisoformat(task_match.group("start"))
            task.due_date = due_from_duration(task.start_date, int(task_match.group("duration")))
            raw_status = task_match.group("status") or ""
            status_tokens = [token.strip() for token in raw_status.split(",") if token.strip()]
            task.blocked = "crit" in status_tokens
            if "done" in status_tokens:
                task.column = "Done"
            elif "crit" in status_tokens and "Blocked" in project.board_columns:
                task.column = "Blocked"
            elif "active" in status_tokens and "In Progress" in project.board_columns:
                task.column = "In Progress"
            elif current_section and current_section in project.board_columns:
                task.column = current_section
            task_positions.append(task.id)
            imported.append(f"Updated task '{task.title}' from timeline")
            continue
        if line.startswith(("gantt", "title ", "dateFormat ", "axisFormat ")):
            continue
        supported = False
        errors.append(f"Unsupported Mermaid line skipped: {raw_line}")

    if task_positions:
        ordering = {task_id: index for index, task_id in enumerate(task_positions)}
        project.tasks.sort(key=lambda item: ordering.get(item.id, len(ordering)))
    return project, imported, errors, supported
