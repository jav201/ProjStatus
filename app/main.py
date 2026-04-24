from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown import markdown

from app.config import AppConfig
from app.models import (
    AccessCategory,
    AccessLink,
    ExportFormat,
    ExportRequest,
    HealthStatus,
    Milestone,
    Person,
    Priority,
    Project,
    ProjectStatus,
    Task,
)
from app.services.exports import ExportService
from app.services.mermaid import import_timeline, render_timeline
from app.services.storage import SECTION_NAMES, StorageService
from app.utils import format_date, parse_date


def create_app(root_dir: Path | None = None) -> FastAPI:
    code_root = Path(__file__).resolve().parents[1]
    data_root = (root_dir or code_root).resolve()
    config = AppConfig(
        root_dir=data_root,
        projects_dir=data_root / "projects",
        exports_dir=data_root / "exports",
        static_dir=code_root / "app" / "static",
        templates_dir=code_root / "app" / "templates",
    )
    storage = StorageService(config)
    exports = ExportService(config, storage)

    app = FastAPI(title="ProjStatus")
    templates = Jinja2Templates(directory=str(config.templates_dir))
    templates.env.filters["markdownify"] = render_markdown
    templates.env.globals["format_date"] = format_date

    app.state.config = config
    app.state.storage = storage
    app.state.exports = exports
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=config.static_dir), name="static")

    @app.get("/", response_class=HTMLResponse, name="dashboard")
    async def dashboard(
        request: Request,
        search: str = "",
        health: str = "",
        sort: str = "recent_update",
        show_archived: str = "",
    ) -> HTMLResponse:
        include_archived = is_truthy(show_archived)
        projects = storage.list_dashboard_projects(search=search, health=health, sort_by=sort, include_archived=include_archived)
        recent_addendums = storage.list_recent_addendums(limit=8, include_archived=include_archived)
        upcoming_milestones: list[tuple[str, Any]] = []
        blocked_tasks: list[tuple[str, Task]] = []
        today = date.today()
        due_soon = 0

        for project_entry in projects:
            loaded = storage.load_project(project_entry.slug)
            for milestone in sorted(
                [item for item in loaded.project.milestones if item.target_date],
                key=lambda item: item.target_date or date.max,
            )[:3]:
                upcoming_milestones.append((loaded.project.slug, milestone))
                if milestone.target_date and milestone.target_date <= today + timedelta(days=7):
                    due_soon += 1
            for task in loaded.project.tasks:
                if task.blocked or task.column == "Blocked":
                    blocked_tasks.append((loaded.project.slug, task))

        summary_cards = {
            "on_track": sum(1 for item in projects if item.health.value == "on-track"),
            "at_risk": sum(1 for item in projects if item.health.value == "at-risk"),
            "blocked": sum(1 for item in projects if item.roadblock_count > 0 or item.health.value == "blocked"),
            "due_soon": due_soon,
        }
        context = {
            "projects": projects,
            "summary_cards": summary_cards,
            "recent_addendums": recent_addendums,
            "upcoming_milestones": sorted(upcoming_milestones, key=lambda item: item[1].target_date or date.max)[:8],
            "blocked_tasks": blocked_tasks[:8],
            "search": search,
            "health": health,
            "sort": sort,
            "show_archived": include_archived,
        }
        return render_template(request, "dashboard.html", context)

    @app.get("/projects/new", response_class=HTMLResponse, name="project_new")
    async def new_project(request: Request) -> HTMLResponse:
        return render_template(request, "new_project.html", {})

    @app.post("/projects/new", name="project_create")
    async def create_project(
        request: Request,
        name: str = Form(...),
        description: str = Form(""),
        start_date_value: str = Form("", alias="start_date"),
        end_date_value: str = Form("", alias="end_date"),
    ) -> RedirectResponse:
        project = storage.create_project(
            name=name.strip(),
            description=description.strip(),
            start_date=parse_date(start_date_value),
            end_date=parse_date(end_date_value),
        )
        return redirect_to(request.url_for("project_overview", slug=project.slug), "Project created.", "success")

    @app.get("/projects/{slug}", response_class=HTMLResponse, name="project_overview")
    async def project_overview(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "overview")

    @app.get("/projects/{slug}/board", response_class=HTMLResponse, name="project_board")
    async def project_board(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "board")

    @app.get("/projects/{slug}/timeline", response_class=HTMLResponse, name="project_timeline")
    async def project_timeline(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "timeline")

    @app.get("/projects/{slug}/view", response_class=HTMLResponse, name="project_view")
    async def project_view(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "view_mode")

    @app.get("/projects/{slug}/people-access", response_class=HTMLResponse, name="project_people_access")
    async def project_people_access(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "people_access")

    @app.get("/projects/{slug}/sections/{section}", response_class=HTMLResponse, name="project_section")
    async def project_section(request: Request, slug: str, section: str) -> HTMLResponse:
        section_name = validate_section(section)
        return await render_project_page(request, slug, "sections", section_name=section_name)

    @app.get("/projects/{slug}/history", response_class=HTMLResponse, name="project_history")
    async def project_history(request: Request, slug: str, entry: str = "") -> HTMLResponse:
        return await render_project_page(request, slug, "history", entry_id=entry)

    @app.post("/projects/{slug}/meta", name="project_meta_update")
    async def update_project_meta(
        request: Request,
        slug: str,
        name: str = Form(...),
        description: str = Form(""),
        logo_path: str = Form(""),
        health: str = Form(...),
        status: str = Form(...),
        start_date_value: str = Form("", alias="start_date"),
        end_date_value: str = Form("", alias="end_date"),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        loaded.project.name = name.strip()
        loaded.project.description = description.strip()
        loaded.project.logo_path = logo_path.strip() or None
        loaded.project.health = HealthStatus(health)
        loaded.project.status = ProjectStatus(status)
        loaded.project.start_date = parse_date(start_date_value)
        loaded.project.end_date = parse_date(end_date_value)
        preserve_timeline = not loaded.project.sync_state.timeline_is_app_owned
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or "Updated project details",
            preserve_timeline=preserve_timeline,
        )
        return redirect_to(request.url_for("project_overview", slug=slug), "Project details saved.", "success")

    @app.post("/projects/{slug}/archive", name="project_archive")
    async def archive_project(
        request: Request,
        slug: str,
        change_note: str = Form(""),
        return_to: str = Form(""),
    ) -> RedirectResponse:
        storage.archive_project(slug, note=change_note)
        destination = safe_return_to(return_to, request.url_for("project_overview", slug=slug))
        return redirect_to(destination, "Project archived.", "success")

    @app.post("/projects/{slug}/unarchive", name="project_unarchive")
    async def unarchive_project(
        request: Request,
        slug: str,
        change_note: str = Form(""),
        return_to: str = Form(""),
    ) -> RedirectResponse:
        storage.unarchive_project(slug, note=change_note)
        destination = safe_return_to(return_to, request.url_for("project_overview", slug=slug))
        return redirect_to(destination, "Project restored to the active list.", "success")

    @app.post("/projects/{slug}/duplicate", name="project_duplicate")
    async def duplicate_project(
        request: Request,
        slug: str,
        new_name: str = Form(""),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        duplicated = storage.duplicate_project(slug, new_name=new_name, note=change_note)
        return redirect_to(
            request.url_for("project_overview", slug=duplicated.slug),
            f"Created duplicate project '{duplicated.name}'.",
            "success",
        )

    @app.post("/projects/{slug}/delete", name="project_delete")
    async def delete_project(
        request: Request,
        slug: str,
        confirm_name: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        if confirm_name.strip() != loaded.project.name:
            return redirect_to(
                request.url_for("project_overview", slug=slug),
                "Type the exact project name before deleting it.",
                "error",
            )
        storage.delete_project(slug)
        return redirect_to(request.url_for("dashboard"), f"Deleted project '{loaded.project.name}'.", "success")

    @app.post("/projects/{slug}/milestones", name="milestone_create")
    async def create_milestone(
        request: Request,
        slug: str,
        title: str = Form(...),
        owner_person_id: str = Form(""),
        target_date_value: str = Form("", alias="target_date"),
        status: str = Form("planned"),
        notes: str = Form(""),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        loaded.project.milestones.append(
            Milestone(
                title=title.strip(),
                owner_person_id=owner_person_id or None,
                target_date=parse_date(target_date_value),
                status=status,
                notes=notes.strip(),
            )
        )
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Added milestone '{title.strip()}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_overview", slug=slug), "Milestone added.", "success")

    @app.post("/projects/{slug}/milestones/{milestone_id}", name="milestone_update")
    async def update_milestone(
        request: Request,
        slug: str,
        milestone_id: str,
        title: str = Form(...),
        owner_person_id: str = Form(""),
        target_date_value: str = Form("", alias="target_date"),
        status: str = Form("planned"),
        notes: str = Form(""),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        milestone = find_item(loaded.project.milestones, milestone_id)
        milestone.title = title.strip()
        milestone.owner_person_id = owner_person_id or None
        milestone.target_date = parse_date(target_date_value)
        milestone.status = status
        milestone.notes = notes.strip()
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Updated milestone '{milestone.title}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_overview", slug=slug), "Milestone updated.", "success")

    @app.post("/projects/{slug}/milestones/{milestone_id}/delete", name="milestone_delete")
    async def delete_milestone(request: Request, slug: str, milestone_id: str, change_note: str = Form("")) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        loaded.project.milestones = [item for item in loaded.project.milestones if item.id != milestone_id]
        for task in loaded.project.tasks:
            if task.milestone_id == milestone_id:
                task.milestone_id = None
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or "Deleted milestone",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_overview", slug=slug), "Milestone deleted.", "success")

    @app.post("/projects/{slug}/tasks", name="task_create")
    async def create_task(request: Request, slug: str) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        form = await request.form()
        title = str(form.get("title", "")).strip()
        task = Task(
            title=title,
            description=str(form.get("description", "")).strip(),
            column=str(form.get("column", loaded.project.board_columns[0])),
            assignee_ids=form.getlist("assignee_ids"),
            start_date=parse_date(str(form.get("start_date", ""))),
            due_date=parse_date(str(form.get("due_date", ""))),
            milestone_id=str(form.get("milestone_id", "")) or None,
            priority=str(form.get("priority", Priority.MEDIUM.value)),
            blocked=str(form.get("blocked", "")) == "on",
            notes=str(form.get("notes", "")).strip(),
        )
        loaded.project.tasks.append(task)
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=str(form.get("change_note", "")).strip() or f"Added task '{title}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_board", slug=slug), "Task added.", "success")

    @app.post("/projects/{slug}/tasks/{task_id}", name="task_update")
    async def update_task(request: Request, slug: str, task_id: str) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        form = await request.form()
        task = find_item(loaded.project.tasks, task_id)
        task.title = str(form.get("title", "")).strip()
        task.description = str(form.get("description", "")).strip()
        task.column = str(form.get("column", task.column))
        task.assignee_ids = [str(item) for item in form.getlist("assignee_ids")]
        task.start_date = parse_date(str(form.get("start_date", "")))
        task.due_date = parse_date(str(form.get("due_date", "")))
        task.milestone_id = str(form.get("milestone_id", "")) or None
        task.priority = str(form.get("priority", Priority.MEDIUM.value))
        task.blocked = str(form.get("blocked", "")) == "on"
        task.notes = str(form.get("notes", "")).strip()
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=str(form.get("change_note", "")).strip() or f"Updated task '{task.title}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_board", slug=slug), "Task updated.", "success")

    @app.post("/projects/{slug}/tasks/{task_id}/delete", name="task_delete")
    async def delete_task(request: Request, slug: str, task_id: str, change_note: str = Form("")) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        loaded.project.tasks = [item for item in loaded.project.tasks if item.id != task_id]
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or "Deleted task",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_board", slug=slug), "Task deleted.", "success")

    @app.post("/projects/{slug}/tasks/{task_id}/move", response_class=JSONResponse, name="task_move")
    async def move_task(request: Request, slug: str, task_id: str) -> JSONResponse:
        loaded = safe_load_project(storage, slug)
        payload = await request.json()
        column = str(payload.get("column", ""))
        if column not in loaded.project.board_columns:
            return JSONResponse({"ok": False, "message": "Unknown board column."}, status_code=400)
        task = find_item(loaded.project.tasks, task_id)
        task.column = column
        task.blocked = column == "Blocked"
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=f"Moved task '{task.title}' to {column}",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return JSONResponse({"ok": True, "column": column})

    @app.post("/projects/{slug}/people", name="person_create")
    async def create_person(
        request: Request,
        slug: str,
        name: str = Form(...),
        email: str = Form(...),
        role: str = Form(...),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        loaded.project.people.append(Person(name=name.strip(), email=email.strip(), role=role.strip()))
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Added person '{name.strip()}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_people_access", slug=slug), "Person added.", "success")

    @app.post("/projects/{slug}/people/{person_id}", name="person_update")
    async def update_person(
        request: Request,
        slug: str,
        person_id: str,
        name: str = Form(...),
        email: str = Form(...),
        role: str = Form(...),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        person = find_item(loaded.project.people, person_id)
        person.name = name.strip()
        person.email = email.strip()
        person.role = role.strip()
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Updated person '{person.name}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_people_access", slug=slug), "Person updated.", "success")

    @app.post("/projects/{slug}/people/{person_id}/delete", name="person_delete")
    async def delete_person(
        request: Request,
        slug: str,
        person_id: str,
        replacement_person_id: str = Form(""),
        clear_assignments: str = Form(""),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        assignments = count_assignments(loaded.project, person_id)
        should_clear = clear_assignments == "on"
        if assignments and not (replacement_person_id or should_clear):
            return redirect_to(
                request.url_for("project_people_access", slug=slug),
                "This person still owns project items. Choose a replacement or clear assignments before deleting.",
                "error",
            )
        for milestone in loaded.project.milestones:
            if milestone.owner_person_id == person_id:
                milestone.owner_person_id = replacement_person_id or None
        for task in loaded.project.tasks:
            if person_id in task.assignee_ids:
                if replacement_person_id:
                    task.assignee_ids = [replacement_person_id if item == person_id else item for item in task.assignee_ids]
                else:
                    task.assignee_ids = [item for item in task.assignee_ids if item != person_id]
        for category in loaded.project.access_links:
            for link in category.links:
                if link.owner_person_id == person_id:
                    link.owner_person_id = replacement_person_id or None
        loaded.project.people = [item for item in loaded.project.people if item.id != person_id]
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or "Deleted person",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_people_access", slug=slug), "Person deleted.", "success")

    @app.post("/projects/{slug}/access-categories", name="access_category_create")
    async def create_access_category(
        request: Request,
        slug: str,
        name: str = Form(...),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        loaded.project.access_links.append(AccessCategory(name=name.strip()))
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Added access category '{name.strip()}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_people_access", slug=slug), "Access category added.", "success")

    @app.post("/projects/{slug}/access-categories/{category_id}", name="access_category_update")
    async def update_access_category(
        request: Request,
        slug: str,
        category_id: str,
        name: str = Form(...),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        category = find_item(loaded.project.access_links, category_id)
        category.name = name.strip()
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Renamed access category to '{category.name}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_people_access", slug=slug), "Access category updated.", "success")

    @app.post("/projects/{slug}/access-categories/{category_id}/delete", name="access_category_delete")
    async def delete_access_category(
        request: Request,
        slug: str,
        category_id: str,
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        category = find_item(loaded.project.access_links, category_id)
        if category.links:
            return redirect_to(
                request.url_for("project_people_access", slug=slug),
                "Remove links from a category before deleting it.",
                "error",
            )
        loaded.project.access_links = [item for item in loaded.project.access_links if item.id != category_id]
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or "Deleted access category",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_people_access", slug=slug), "Access category deleted.", "success")

    @app.post("/projects/{slug}/access-categories/{category_id}/links", name="access_link_create")
    async def create_access_link(
        request: Request,
        slug: str,
        category_id: str,
        label: str = Form(...),
        url: str = Form(...),
        notes: str = Form(""),
        owner_person_id: str = Form(""),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        category = find_item(loaded.project.access_links, category_id)
        category.links.append(
            AccessLink(label=label.strip(), url=url.strip(), notes=notes.strip(), owner_person_id=owner_person_id or None)
        )
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Added access link '{label.strip()}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_people_access", slug=slug), "Access link added.", "success")

    @app.post("/projects/{slug}/access-categories/{category_id}/links/{link_id}", name="access_link_update")
    async def update_access_link(
        request: Request,
        slug: str,
        category_id: str,
        link_id: str,
        label: str = Form(...),
        url: str = Form(...),
        notes: str = Form(""),
        owner_person_id: str = Form(""),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        category = find_item(loaded.project.access_links, category_id)
        link = find_item(category.links, link_id)
        link.label = label.strip()
        link.url = url.strip()
        link.notes = notes.strip()
        link.owner_person_id = owner_person_id or None
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Updated access link '{link.label}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_people_access", slug=slug), "Access link updated.", "success")

    @app.post("/projects/{slug}/access-categories/{category_id}/links/{link_id}/delete", name="access_link_delete")
    async def delete_access_link(
        request: Request,
        slug: str,
        category_id: str,
        link_id: str,
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        category = find_item(loaded.project.access_links, category_id)
        category.links = [item for item in category.links if item.id != link_id]
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or "Deleted access link",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_people_access", slug=slug), "Access link deleted.", "success")

    @app.post("/projects/{slug}/sections/{section}", name="section_save")
    async def save_section(
        request: Request,
        slug: str,
        section: str,
        body: str = Form(""),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        section_name = validate_section(section)
        loaded = safe_load_project(storage, slug)
        loaded.sections[section_name] = body
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Updated {section_name.replace('_', ' ')}",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_section", slug=slug, section=section_name), "Section saved.", "success")

    @app.post("/projects/{slug}/timeline", name="timeline_save")
    async def save_timeline(
        request: Request,
        slug: str,
        timeline_text: str = Form(""),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        imported_project, imported, errors, supported = import_timeline(loaded.project.model_copy(deep=True), timeline_text)
        if supported and not errors:
            storage.save_project(
                imported_project,
                loaded.sections,
                note=change_note.strip() or "Updated timeline",
                timeline_text=timeline_text,
            )
            message = "Timeline saved and synced into project data."
            level = "success"
        else:
            storage.save_project(
                loaded.project,
                loaded.sections,
                note=change_note.strip() or "Saved timeline as visual-only update",
                timeline_text=timeline_text,
                preserve_timeline=True,
            )
            message = "Timeline saved, but unsupported Mermaid changes were preserved as visual-only content."
            level = "warning"
        return redirect_to(request.url_for("project_timeline", slug=slug), message, level)

    @app.post("/projects/{slug}/timeline/regenerate", name="timeline_regenerate")
    async def regenerate_timeline(
        request: Request,
        slug: str,
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or "Regenerated timeline from project data",
            timeline_text=render_timeline(loaded.project),
        )
        return redirect_to(request.url_for("project_timeline", slug=slug), "Timeline regenerated.", "success")

    @app.post("/projects/{slug}/history/{addendum_id}/restore", name="history_restore")
    async def restore_history(
        request: Request,
        slug: str,
        addendum_id: str,
        change_note: str = Form(""),
    ) -> RedirectResponse:
        storage.restore_history(slug, addendum_id, note=change_note.strip() or "")
        return redirect_to(request.url_for("project_history", slug=slug), "Snapshot restored as a new addendum.", "success")

    @app.get("/projects/{slug}/logo", name="project_logo")
    async def project_logo(slug: str) -> FileResponse:
        loaded = safe_load_project(storage, slug)
        logo_file = storage.resolve_logo_file(loaded.project)
        if logo_file is None:
            raise HTTPException(status_code=404, detail="Logo not found")
        return FileResponse(logo_file)

    @app.get("/exports", response_class=HTMLResponse, name="exports")
    async def export_page(request: Request, project: str = "") -> HTMLResponse:
        projects = storage.list_dashboard_projects(sort_by="name", include_archived=True)
        selected = [project] if project else []
        return render_template(request, "exports.html", {"projects": projects, "selected_projects": selected, "results": [], "batch_dir": ""})

    @app.post("/exports", response_class=HTMLResponse, name="exports_run")
    async def run_exports(request: Request) -> HTMLResponse:
        form = await request.form()
        project_slugs = [str(item) for item in form.getlist("project_slugs")]
        formats = [ExportFormat(value) for value in form.getlist("formats")]
        if not project_slugs or not formats:
            return render_template(
                request,
                "exports.html",
                {
                    "projects": storage.list_dashboard_projects(sort_by="name", include_archived=True),
                    "selected_projects": project_slugs,
                    "results": [],
                    "batch_dir": "",
                    "message": "Select at least one project and one export format.",
                    "message_level": "error",
                },
            )
        batch_dir, results = exports.run(ExportRequest(project_slugs=project_slugs, formats=formats))
        return render_template(
            request,
            "exports.html",
            {
                "projects": storage.list_dashboard_projects(sort_by="name", include_archived=True),
                "selected_projects": project_slugs,
                "selected_formats": [item.value for item in formats],
                "results": results,
                "batch_dir": str(batch_dir),
                "message": "Export run finished.",
                "message_level": "success",
            },
        )

    @app.post("/preview/markdown", response_class=HTMLResponse, name="markdown_preview")
    async def markdown_preview(body: str = Form("")) -> HTMLResponse:
        return HTMLResponse(render_markdown(body))

    async def render_project_page(
        request: Request,
        slug: str,
        active_tab: str,
        section_name: str = "content",
        entry_id: str = "",
    ) -> HTMLResponse:
        loaded = safe_load_project(storage, slug)
        people_map = {person.id: person for person in loaded.project.people}
        milestone_map = {milestone.id: milestone for milestone in loaded.project.milestones}
        assignment_counts = {person.id: count_assignments(loaded.project, person.id) for person in loaded.project.people}
        tasks_by_column = {column: [task for task in loaded.project.tasks if task.column == column] for column in loaded.project.board_columns}
        selected_addendum = loaded.addendums[0] if loaded.addendums else None
        if entry_id:
            selected_addendum = next((item for item in loaded.addendums if item.id == entry_id), selected_addendum)
        logo_url = str(request.url_for("project_logo", slug=loaded.project.slug)) if storage.resolve_logo_file(loaded.project) else ""

        context = {
            "project": loaded.project,
            "project_logo_url": logo_url,
            "sections": loaded.sections,
            "timeline_text": loaded.timeline_text,
            "active_tab": active_tab,
            "section_name": section_name,
            "selected_addendum": selected_addendum,
            "people_map": people_map,
            "milestone_map": milestone_map,
            "assignment_counts": assignment_counts,
            "tasks_by_column": tasks_by_column,
            "all_tasks": loaded.project.tasks,
            "all_addendums": loaded.addendums,
            "upcoming_milestones": sorted(
                [item for item in loaded.project.milestones if item.target_date],
                key=lambda item: item.target_date or date.max,
            ),
            "blocked_tasks": [task for task in loaded.project.tasks if task.blocked or task.column == "Blocked"],
            "import_summary": loaded.import_summary,
            "validation_errors": loaded.validation_errors,
            "sync_notice": loaded.sync_notice,
            "tab_template": tab_template(active_tab),
            "export_mode": False,
        }
        return render_template(request, "project.html", context)

    return app


def render_markdown(value: str) -> str:
    return markdown(value or "", extensions=["fenced_code", "tables", "sane_lists"])


def render_template(request: Request, template_name: str, context: dict[str, Any]) -> HTMLResponse:
    templates: Jinja2Templates = request.app.state.templates
    merged = {
        "request": request,
        "message": context.get("message", request.query_params.get("message", "")),
        "message_level": context.get("message_level", request.query_params.get("level", "info")),
    }
    merged.update(context)
    return templates.TemplateResponse(request, template_name, merged)


def redirect_to(url: str | Any, message: str, level: str) -> RedirectResponse:
    url = str(url)
    separator = "&" if "?" in url else "?"
    query = urlencode({"message": message, "level": level})
    return RedirectResponse(f"{url}{separator}{query}", status_code=303)


def safe_return_to(return_to: str, fallback: str | Any) -> str:
    target = str(return_to or "")
    if target.startswith("/"):
        return target
    return str(fallback)


def validate_section(section: str) -> str:
    if section not in SECTION_NAMES:
        raise HTTPException(status_code=404, detail="Unknown section")
    return section


def safe_load_project(storage: StorageService, slug: str):
    try:
        return storage.load_project(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


def is_truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "on", "yes"}


def find_item(items: list[Any], item_id: str) -> Any:
    for item in items:
        if getattr(item, "id", None) == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")


def count_assignments(project: Project, person_id: str) -> int:
    total = 0
    total += sum(1 for milestone in project.milestones if milestone.owner_person_id == person_id)
    total += sum(1 for task in project.tasks if person_id in task.assignee_ids)
    total += sum(1 for category in project.access_links for link in category.links if link.owner_person_id == person_id)
    return total


def tab_template(active_tab: str) -> str:
    mapping = {
        "overview": "partials/project_overview.html",
        "board": "partials/project_board.html",
        "timeline": "partials/project_timeline.html",
        "view_mode": "partials/project_view_mode.html",
        "people_access": "partials/project_people_access.html",
        "sections": "partials/project_section.html",
        "history": "partials/project_history.html",
    }
    return mapping[active_tab]


app = create_app()
