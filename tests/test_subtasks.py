from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import AppConfig
from app.main import create_app, progress_pct, task_completion
from app.models import Subtask, Task
from app.services.storage import StorageService


def _storage(tmp_path: Path) -> StorageService:
    return StorageService(AppConfig.from_root(tmp_path))


def test_done_column_overrides_subtasks() -> None:
    task = Task(
        title="Done thing",
        column="Done",
        subtasks=[Subtask(title="a", done=False), Subtask(title="b", done=False), Subtask(title="c", done=False)],
    )
    assert task_completion(task) == 1.0


def test_partial_subtasks_count_for_non_done_task() -> None:
    task = Task(
        title="Half-done",
        column="In Progress",
        subtasks=[Subtask(title="a", done=True), Subtask(title="b", done=True), Subtask(title="c", done=False), Subtask(title="d", done=False)],
    )
    assert task_completion(task) == 0.5


def test_no_subtasks_no_progress_unless_done() -> None:
    backlog = Task(title="Pending", column="Backlog")
    in_progress = Task(title="WIP", column="In Progress")
    done = Task(title="Shipped", column="Done")
    assert task_completion(backlog) == 0.0
    assert task_completion(in_progress) == 0.0
    assert task_completion(done) == 1.0


def test_progress_pct_averages_task_completion(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    project = storage.create_project("Average")
    project.tasks = [
        Task(title="Shipped", column="Done"),
        Task(
            title="Half",
            column="In Progress",
            subtasks=[Subtask(title="a", done=True), Subtask(title="b", done=True), Subtask(title="c", done=False), Subtask(title="d", done=False)],
        ),
        Task(title="Untouched", column="Backlog"),
    ]
    storage.save_project(project, {"content": "", "change_requests": "", "roadblocks": "", "notes": ""})
    loaded = storage.load_project(project.slug)
    assert progress_pct(loaded.project) == (1.0 + 0.5 + 0.0) / 3


def test_progress_pct_zero_for_empty_project(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    project = storage.create_project("Empty")
    assert progress_pct(project) == 0.0


def test_subtasks_round_trip_through_save_load(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    project = storage.create_project("Round Trip")
    task = Task(
        title="With subtasks",
        column="In Progress",
        subtasks=[Subtask(title="Step one", done=True), Subtask(title="Step two", done=False)],
    )
    project.tasks.append(task)
    storage.save_project(project, {"content": "", "change_requests": "", "roadblocks": "", "notes": ""})

    loaded = storage.load_project(project.slug)
    assert len(loaded.project.tasks) == 1
    saved_subs = loaded.project.tasks[0].subtasks
    assert [(s.title, s.done) for s in saved_subs] == [("Step one", True), ("Step two", False)]
    # IDs are preserved (not regenerated on reload)
    assert saved_subs[0].id == task.subtasks[0].id


def test_legacy_task_without_subtasks_field_loads(tmp_path: Path) -> None:
    """A project.json written before subtasks existed must load with subtasks=[]."""
    storage = _storage(tmp_path)
    project = storage.create_project("Legacy")
    project.tasks.append(Task(title="Old task", column="Backlog"))
    storage.save_project(project, {"content": "", "change_requests": "", "roadblocks": "", "notes": ""})

    project_json = tmp_path / "projects" / project.slug / "project.json"
    payload = json.loads(project_json.read_text(encoding="utf-8"))
    for raw_task in payload["tasks"]:
        raw_task.pop("subtasks", None)
    project_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    loaded = storage.load_project(project.slug)
    assert loaded.project.tasks[0].subtasks == []


def test_subtasks_survive_external_timeline_edit(tmp_path: Path) -> None:
    """Mermaid round-trip ignores subtasks; an external timeline edit must not lose them."""
    storage = _storage(tmp_path)
    project = storage.create_project("Mermaid Safe")
    task = Task(
        title="With subs",
        column="In Progress",
        start_date="2026-04-24",
        due_date="2026-04-26",
        subtasks=[Subtask(title="step", done=True)],
    )
    project.tasks.append(task)
    storage.save_project(project, {"content": "", "change_requests": "", "roadblocks": "", "notes": ""})

    project_dir = tmp_path / "projects" / project.slug
    timeline = (project_dir / "timeline.mmd").read_text(encoding="utf-8")
    edited = timeline.replace("With subs", "With subs revised")
    (project_dir / "timeline.mmd").write_text(edited, encoding="utf-8")

    refreshed = storage.load_project(project.slug)
    only_task = refreshed.project.tasks[0]
    assert only_task.title == "With subs revised"
    assert [(s.title, s.done) for s in only_task.subtasks] == [("step", True)]


def test_task_update_route_persists_subtasks(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    client.post("/projects/new", data={"name": "Subtask Flow"}, follow_redirects=True)
    client.post(
        "/projects/subtask-flow/tasks",
        data={"title": "Shippable", "column": "In Progress", "priority": "medium"},
        follow_redirects=True,
    )

    storage = _storage(tmp_path)
    task_id = storage.load_project("subtask-flow").project.tasks[0].id

    payload = json.dumps([
        {"id": "", "title": "Draft", "done": True},
        {"id": "", "title": "Review", "done": False},
        {"id": "", "title": "   ", "done": False},  # blank — should be dropped
    ])
    response = client.post(
        f"/projects/subtask-flow/tasks/{task_id}",
        data={
            "title": "Shippable",
            "description": "",
            "column": "In Progress",
            "priority": "medium",
            "start_date": "",
            "due_date": "",
            "milestone_id": "",
            "notes": "",
            "subtasks_json": payload,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    saved = storage.load_project("subtask-flow").project.tasks[0]
    assert [(s.title, s.done) for s in saved.subtasks] == [("Draft", True), ("Review", False)]


def test_milestone_create_from_plan_redirects_to_board(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    client.post("/projects/new", data={"name": "Plan Redirect"}, follow_redirects=True)

    plan = client.post(
        "/projects/plan-redirect/milestones",
        data={"title": "Kickoff", "target_date": "2026-05-01", "status": "planned", "return_to": "plan"},
        follow_redirects=False,
    )
    assert plan.status_code == 303
    assert "/projects/plan-redirect/board" in plan.headers["location"]

    summary = client.post(
        "/projects/plan-redirect/milestones",
        data={"title": "Cutover", "target_date": "2026-06-01", "status": "planned"},
        follow_redirects=False,
    )
    assert summary.status_code == 303
    assert "/projects/plan-redirect" in summary.headers["location"]
    assert "/board" not in summary.headers["location"]


def test_plan_tab_renders_add_dropdown(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    client.post("/projects/new", data={"name": "Dropdown Project"}, follow_redirects=True)
    board = client.get("/projects/dropdown-project/board")
    assert board.status_code == 200
    assert 'data-add-open="task"' in board.text
    assert 'data-add-open="milestone"' in board.text
    assert 'data-add-panel="task"' in board.text
    assert 'data-add-panel="milestone"' in board.text

    timeline = client.get("/projects/dropdown-project/timeline")
    assert timeline.status_code == 200
    assert 'data-add-open="milestone"' in timeline.text
