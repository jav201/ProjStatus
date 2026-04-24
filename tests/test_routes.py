from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(tmp_path)
    return TestClient(app)


def test_dashboard_and_project_creation_flow(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/")
    assert response.status_code == 200
    assert "Create project" in response.text

    create = client.post(
        "/projects/new",
        data={
            "name": "Launch Control",
            "description": "Coordinate release work",
            "start_date": "2026-04-23",
            "end_date": "2026-05-10",
        },
        follow_redirects=False,
    )
    assert create.status_code == 303

    redirect_location = create.headers["location"]
    page = client.get(redirect_location)
    assert page.status_code == 200
    assert "Launch Control" in page.text
    assert (tmp_path / "projects" / "launch-control" / "project.json").exists()


def test_people_access_and_exports_pages_render(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.post("/projects/new", data={"name": "Ops Hub"}, follow_redirects=True)

    person = client.post(
        "/projects/ops-hub/people",
        data={"name": "Alex Roe", "email": "alex@example.com", "role": "Project Manager"},
        follow_redirects=True,
    )
    assert person.status_code == 200
    assert "Alex Roe" in person.text

    category = client.post(
        "/projects/ops-hub/access-categories",
        data={"name": "Shared Drives"},
        follow_redirects=True,
    )
    assert category.status_code == 200
    assert "Shared Drives" in category.text

    exports = client.get("/exports")
    assert exports.status_code == 200
    assert "Ops Hub" in exports.text

    project_view = client.get("/projects/ops-hub/view")
    assert project_view.status_code == 200
    assert "Executive snapshot" in project_view.text


def test_markdown_preview_endpoint(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    preview = client.post("/preview/markdown", data={"body": "# Hello\n\nWorld"})

    assert preview.status_code == 200
    assert "<h1>Hello</h1>" in preview.text
