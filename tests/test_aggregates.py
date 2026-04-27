"""Routes for /inbox and /risks aggregate views, plus KPI history."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import HealthStatus, Milestone, MilestoneStatus, Priority, Task


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(tmp_path)
    return TestClient(app)


def _make_project(client: TestClient, name: str, *, health: str = "on-track") -> str:
    response = client.post(
        "/projects/new",
        data={"name": name, "description": f"{name} desc", "start_date": "2026-04-01", "end_date": "2026-06-30"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    # location is "http://testserver/projects/<slug>?message=..." or relative "/projects/<slug>?..."
    path = location.split("?")[0]
    slug = path.rstrip("/").split("/projects/")[-1]
    if health != "on-track":
        client.post(
            f"/projects/{slug}/meta",
            data={
                "name": name,
                "description": f"{name} desc",
                "logo_path": "",
                "health": health,
                "status": "active",
                "start_date": "2026-04-01",
                "end_date": "2026-06-30",
                "change_note": f"set {health}",
            },
            follow_redirects=False,
        )
    return slug


def test_inbox_lists_recent_addendums_grouped_by_day(client: TestClient) -> None:
    _make_project(client, "Alpha")
    _make_project(client, "Beta")
    response = client.get("/inbox")
    assert response.status_code == 200
    assert "Alpha" in response.text or "alpha" in response.text
    assert "Beta" in response.text or "beta" in response.text
    # at least one day-heading bucket
    assert "day-heading" in response.text


def test_inbox_unread_filter_uses_24h_cutoff(client: TestClient) -> None:
    _make_project(client, "Charlie")
    response = client.get("/inbox?filter=unread")
    assert response.status_code == 200
    # the just-saved project should appear under unread (within 24h)
    assert "Charlie" in response.text or "charlie" in response.text


def test_risks_aggregates_blocked_tasks_across_projects(client: TestClient) -> None:
    slug_a = _make_project(client, "Delta")
    slug_b = _make_project(client, "Echo")
    client.post(
        f"/projects/{slug_a}/tasks",
        data={"title": "Stuck thing", "column": "Blocked", "priority": "high", "blocked": "on", "notes": "Waiting on legal"},
        follow_redirects=False,
    )
    client.post(
        f"/projects/{slug_b}/tasks",
        data={"title": "Another blocker", "column": "Blocked", "priority": "medium"},
        follow_redirects=False,
    )
    response = client.get("/risks")
    assert response.status_code == 200
    assert "Stuck thing" in response.text
    assert "Another blocker" in response.text
    assert "Blocked tasks" in response.text


def test_risks_includes_roadblock_markdown(client: TestClient) -> None:
    slug = _make_project(client, "Foxtrot")
    client.post(
        f"/projects/{slug}/sections/roadblocks",
        data={"body": "## Open issues\n\n- Vendor delay\n- Permit pending"},
        follow_redirects=False,
    )
    response = client.get("/risks")
    assert response.status_code == 200
    assert "Roadblock notes" in response.text
    assert "Vendor delay" in response.text


def test_sidebar_inbox_count_reflects_recent_activity(client: TestClient) -> None:
    _make_project(client, "Golf")
    response = client.get("/")
    assert response.status_code == 200
    # The inbox badge should appear in the sidebar with at least one item
    assert "sidebar-badge" in response.text


def test_kpi_history_shape(tmp_path: Path) -> None:
    """kpi_snapshot_history returns one entry per day with the four buckets."""
    app = create_app(tmp_path)
    client = TestClient(app)
    _make_project(client, "Hotel", health="at-risk")
    storage = app.state.storage
    history = storage.kpi_snapshot_history(days=14)
    assert len(history) == 14
    for snapshot in history:
        assert set(snapshot) == {"on_track", "at_risk", "blocked", "due_soon"}
    # latest snapshot should reflect the at-risk project
    assert history[-1]["at_risk"] == 1


def test_dashboard_shows_kpi_deltas_and_sparklines(client: TestClient) -> None:
    _make_project(client, "India", health="blocked")
    response = client.get("/")
    assert response.status_code == 200
    assert "kpi-spark" in response.text
    assert "kpi-delta" in response.text
