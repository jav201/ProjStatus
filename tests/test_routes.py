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


def test_project_lifecycle_logo_and_dashboard_filters(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.post("/projects/new", data={"name": "Ops Hub"}, follow_redirects=True)

    logo_path = tmp_path / "projects" / "ops-hub" / "assets" / "logo.png"
    logo_path.parent.mkdir(parents=True, exist_ok=True)
    logo_path.write_bytes(b"fake-png")

    meta = client.post(
        "/projects/ops-hub/meta",
        data={
            "name": "Ops Hub",
            "description": "Coordinate release work",
            "logo_path": "assets/logo.png",
            "health": "on-track",
            "status": "active",
            "start_date": "2026-04-23",
            "end_date": "2026-05-10",
            "change_note": "Added logo",
        },
        follow_redirects=True,
    )
    assert meta.status_code == 200
    assert 'data-theme-toggle' in meta.text
    assert "/projects/ops-hub/logo" in meta.text

    person = client.post(
        "/projects/ops-hub/people",
        data={"name": "Alex Roe", "email": "alex@example.com", "role": "Project Manager"},
        follow_redirects=True,
    )
    assert person.status_code == 200

    dashboard_search = client.get("/?search=Project+Manager")
    assert dashboard_search.status_code == 200
    assert "Ops Hub" in dashboard_search.text

    logo = client.get("/projects/ops-hub/logo")
    assert logo.status_code == 200
    assert logo.content == b"fake-png"

    archive = client.post("/projects/ops-hub/archive", data={"return_to": "/"}, follow_redirects=False)
    assert archive.status_code == 303

    hidden_dashboard = client.get("/")
    assert "Ops Hub" not in hidden_dashboard.text

    archived_dashboard = client.get("/?show_archived=on")
    assert "Ops Hub" in archived_dashboard.text
    assert "Archived" in archived_dashboard.text

    duplicate = client.post(
        "/projects/ops-hub/duplicate",
        data={"new_name": "Ops Hub Copy", "change_note": "Create copy"},
        follow_redirects=False,
    )
    assert duplicate.status_code == 303
    assert (tmp_path / "projects" / "ops-hub-copy" / "project.json").exists()
    assert (tmp_path / "projects" / "ops-hub-copy" / "assets" / "logo.png").exists()

    delete_rejected = client.post(
        "/projects/ops-hub-copy/delete",
        data={"confirm_name": "Wrong Name"},
        follow_redirects=True,
    )
    assert delete_rejected.status_code == 200
    assert "Type the exact project name before deleting it." in delete_rejected.text
    assert (tmp_path / "projects" / "ops-hub-copy").exists()

    delete_ok = client.post(
        "/projects/ops-hub-copy/delete",
        data={"confirm_name": "Ops Hub Copy"},
        follow_redirects=False,
    )
    assert delete_ok.status_code == 303
    assert not (tmp_path / "projects" / "ops-hub-copy").exists()
