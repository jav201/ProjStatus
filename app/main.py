from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown import markdown

from app.config import AppConfig
from app.models import (
    AccessCategory,
    AccessLink,
    DictionaryEntry,
    DocumentFieldType,
    DocumentTemplateField,
    ExportFormat,
    ExportRequest,
    HealthStatus,
    Milestone,
    MilestoneStatus,
    Person,
    Priority,
    Project,
    ProjectStatus,
    Subtask,
    Task,
    make_id,
)
from app.services.exports import ExportService
from app.services.mermaid import import_timeline, render_timeline
from app.services.storage import SECTION_NAMES, StorageService, inspect_docx_tags
from app.utils import format_date, format_when, parse_date, slugify


def create_app(root_dir: Path | None = None) -> FastAPI:
    code_root = Path(__file__).resolve().parents[1]
    data_root = (root_dir or code_root).resolve()
    config = AppConfig(
        root_dir=data_root,
        projects_dir=data_root / "projects",
        exports_dir=data_root / "exports",
        project_templates_dir=data_root / "project_templates",
        document_templates_dir=data_root / "document_templates",
        static_dir=code_root / "app" / "static",
        templates_dir=code_root / "app" / "templates",
    )
    storage = StorageService(config)
    exports = ExportService(config, storage)

    app = FastAPI(title="ProjStatus")
    templates = Jinja2Templates(directory=str(config.templates_dir))
    templates.env.filters["markdownify"] = render_markdown
    templates.env.filters["when"] = format_when
    templates.env.filters["model_list_json"] = model_list_json
    templates.env.globals["format_date"] = format_date
    templates.env.globals["format_when"] = format_when

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
        view: str = "cards",
        show_archived: str = "",
    ) -> HTMLResponse:
        include_archived = is_truthy(show_archived)
        projects = storage.list_dashboard_projects(search=search, health=health, sort_by=sort, include_archived=include_archived)
        recent_addendums = storage.list_recent_addendums(limit=8, include_archived=include_archived)
        upcoming_milestones: list[tuple[str, Any]] = []
        blocked_tasks: list[tuple[str, Task]] = []
        loaded_projects: list[Project] = []
        today = date.today()
        due_soon = 0

        for project_entry in projects:
            loaded = storage.load_project(project_entry.slug)
            loaded_projects.append(loaded.project)
            for milestone in sorted(
                [item for item in loaded.project.milestones if item.target_date],
                key=lambda item: item.target_date or date.max,
            )[:3]:
                upcoming_milestones.append((loaded.project.slug, milestone))
                if milestone.target_date and milestone.target_date <= today + timedelta(days=7):
                    due_soon += 1
            for task in loaded.project.tasks:
                if task.column == "Blocked":
                    blocked_tasks.append((loaded.project.slug, task))

        summary_cards = {
            "on_track": sum(1 for item in projects if item.health.value == "on-track"),
            "at_risk": sum(1 for item in projects if item.health.value == "at-risk"),
            "blocked": sum(1 for item in projects if item.roadblock_count > 0 or item.health.value == "blocked"),
            "due_soon": due_soon,
        }
        kpi_history = storage.kpi_snapshot_history(days=14)
        kpi_series = {
            key: [snapshot[key] for snapshot in kpi_history] for key in ("on_track", "at_risk", "blocked", "due_soon")
        }
        kpi_deltas: dict[str, int] = {}
        cutoff_index = max(len(kpi_history) - 8, 0)
        for key, current in summary_cards.items():
            past = kpi_history[cutoff_index][key] if kpi_history else current
            kpi_deltas[key] = current - past

        slug_to_loaded = {p.slug: p for p in loaded_projects}
        project_cards = []
        for entry in projects:
            project = slug_to_loaded.get(entry.slug)
            if project is None:
                continue
            project_cards.append(
                {
                    "entry": entry,
                    "progress_pct": progress_pct(project),
                    "next_milestone": entry.next_milestone,
                    "owners": entry.owner_names[:3],
                }
            )

        context = {
            "projects": projects,
            "summary_cards": summary_cards,
            "kpi_series": kpi_series,
            "kpi_deltas": kpi_deltas,
            "project_cards": project_cards,
            "recent_addendums": recent_addendums,
            "upcoming_milestones": sorted(upcoming_milestones, key=lambda item: item[1].target_date or date.max)[:8],
            "blocked_tasks": blocked_tasks[:8],
            "search": search,
            "health": health,
            "sort": sort,
            "view": view if view in {"cards", "gantt", "table"} else "cards",
            "show_archived": include_archived,
            "portfolio_gantt": build_portfolio_gantt(loaded_projects, today),
        }
        return render_template(request, "dashboard.html", context)

    @app.get("/inbox", response_class=HTMLResponse, name="inbox")
    async def inbox(request: Request, filter: str = "all") -> HTMLResponse:
        addendums = storage.list_recent_addendums(limit=50, include_archived=False)
        cutoff = datetime.now() - timedelta(hours=24)
        if filter == "last_24h":
            addendums = [(slug, addendum) for slug, addendum in addendums if addendum.created_at >= cutoff]
        groups: dict[str, list[tuple[str, Any]]] = {}
        for slug, addendum in addendums:
            groups.setdefault(addendum.created_at.strftime("%Y-%m-%d"), []).append((slug, addendum))
        sync_notices: list[dict[str, Any]] = []
        for entry in storage.list_dashboard_projects(include_archived=False):
            loaded = storage.load_project(entry.slug)
            if loaded.sync_notice or loaded.validation_errors:
                sync_notices.append(
                    {
                        "slug": entry.slug,
                        "name": entry.name,
                        "sync_notice": loaded.sync_notice,
                        "errors": loaded.validation_errors,
                    }
                )
        return render_template(
            request,
            "inbox.html",
            {
                "addendum_groups": sorted(groups.items(), reverse=True),
                "sync_notices": sync_notices,
                "filter": filter,
                "unread_count": sum(1 for _, addendum in addendums if addendum.created_at >= cutoff),
            },
        )

    @app.get("/risks", response_class=HTMLResponse, name="risks")
    async def risks_and_roadblocks(request: Request) -> HTMLResponse:
        blocked_rows: list[dict[str, Any]] = []
        roadblock_notes: list[dict[str, Any]] = []
        today = date.today()
        for entry in storage.list_dashboard_projects(sort_by="recent_update", include_archived=False):
            loaded = storage.load_project(entry.slug)
            people_map = {person.id: person for person in loaded.project.people}
            for task in loaded.project.tasks:
                if task.column != "Blocked":
                    continue
                blocked_since = days_blocked(loaded.addendums, task.id, today)
                blocked_rows.append(
                    {
                        "task": task,
                        "project_slug": entry.slug,
                        "project_name": entry.name,
                        "days_blocked": blocked_since,
                        "assignees": [people_map[pid] for pid in task.assignee_ids if pid in people_map],
                    }
                )
            roadblocks_text = (loaded.sections.get("roadblocks") or "").strip()
            if roadblocks_text:
                roadblock_notes.append(
                    {
                        "slug": entry.slug,
                        "name": entry.name,
                        "text": roadblocks_text,
                    }
                )
        blocked_rows.sort(key=lambda row: row["days_blocked"] or 0, reverse=True)
        return render_template(
            request,
            "risks.html",
            {
                "blocked_rows": blocked_rows,
                "roadblock_notes": roadblock_notes,
            },
        )

    @app.get("/projects/new", response_class=HTMLResponse, name="project_new")
    async def new_project(request: Request) -> HTMLResponse:
        return render_template(request, "new_project.html", {"project_templates": storage.list_project_templates()})

    @app.post("/projects/new", name="project_create")
    async def create_project(
        request: Request,
        name: str = Form(...),
        description: str = Form(""),
        start_date_value: str = Form("", alias="start_date"),
        end_date_value: str = Form("", alias="end_date"),
        template_slug: str = Form(""),
    ) -> RedirectResponse:
        if template_slug:
            project = storage.create_project_from_template(
                template_slug=template_slug,
                name=name.strip(),
                description=description.strip(),
                start_date=parse_date(start_date_value),
                end_date=parse_date(end_date_value),
            )
        else:
            project = storage.create_project(
                name=name.strip(),
                description=description.strip(),
                start_date=parse_date(start_date_value),
                end_date=parse_date(end_date_value),
            )
        return redirect_to(request.url_for("project_overview", slug=project.slug), "Project created.", "success")

    @app.get("/templates", response_class=HTMLResponse, name="templates")
    async def templates_page(request: Request) -> HTMLResponse:
        document_templates = storage.list_document_templates()
        canonical_fields = build_canonical_field_index(document_templates)
        document_template_views = []
        for template in document_templates:
            docx_path = storage.document_template_docx_path(template)
            tags_found = inspect_docx_tags(docx_path) if docx_path else []
            field_keys = {field.key for field in template.fields}
            builtin_keys = list(BUILTIN_TAG_KEYS)
            document_template_views.append(
                {
                    "template": template,
                    "tags_found": tags_found,
                    "builtin_keys": builtin_keys,
                    "tags_unmapped": [tag for tag in tags_found if tag not in field_keys and tag not in builtin_keys],
                    "fields_unused": [field for field in template.fields if tags_found and field.key not in tags_found],
                    "fields_text": serialize_document_template_fields(template.fields),
                }
            )
        return render_template(
            request,
            "templates.html",
            {
                "projects": storage.list_dashboard_projects(sort_by="name", include_archived=True),
                "project_templates": storage.list_project_templates(),
                "document_templates": document_templates,
                "document_template_views": document_template_views,
                "canonical_fields": canonical_fields,
            },
        )

    @app.post("/templates/projects", name="project_template_create")
    async def create_project_template(
        request: Request,
        project_slug: str = Form(...),
        name: str = Form(...),
        description: str = Form(""),
    ) -> RedirectResponse:
        storage.create_project_template_from_project(project_slug, name.strip(), description.strip())
        return redirect_to(request.url_for("templates"), "Project template created.", "success")

    @app.post("/templates/documents", name="document_template_create")
    async def create_document_template(
        request: Request,
        name: str = Form(...),
        description: str = Form(""),
        fields_text: str = Form(""),
    ) -> RedirectResponse:
        fields = parse_document_template_fields(fields_text)
        storage.create_document_template(name.strip(), description.strip(), fields)
        return redirect_to(request.url_for("templates"), "Document template created.", "success")

    @app.post("/templates/documents/{slug}/upload", name="document_template_upload")
    async def upload_document_template_file(
        request: Request,
        slug: str,
        file: UploadFile = File(...),
    ) -> RedirectResponse:
        try:
            data = await file.read()
            storage.save_document_template_file(slug, file.filename or "template.docx", data)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Document template not found.")
        return redirect_to(request.url_for("templates"), "Word template uploaded.", "success")

    @app.post("/templates/documents/{slug}/file/delete", name="document_template_remove_file")
    async def remove_document_template_file(request: Request, slug: str) -> RedirectResponse:
        try:
            storage.remove_document_template_file(slug)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Document template not found.")
        return redirect_to(request.url_for("templates"), "Word file removed.", "success")

    @app.post("/templates/documents/{slug}/fields", name="document_template_update_fields")
    async def update_document_template_fields(
        request: Request,
        slug: str,
        fields_text: str = Form(""),
    ) -> RedirectResponse:
        try:
            template = storage.load_document_template(slug)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Document template not found.")
        template.fields = parse_document_template_fields(fields_text)
        storage.save_document_template(template)
        return redirect_to(request.url_for("templates"), "Fields updated.", "success")

    @app.post("/templates/documents/{slug}/delete", name="document_template_delete")
    async def delete_document_template(request: Request, slug: str) -> RedirectResponse:
        storage.delete_document_template(slug)
        return redirect_to(request.url_for("templates"), "Document template deleted.", "success")

    @app.post("/templates/documents/{slug}/render", name="document_template_render")
    async def render_document_template(
        request: Request,
        slug: str,
        project_slug: str = Form(...),
    ) -> Response:
        try:
            data, filename = storage.render_document_template(slug, project_slug)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/projects/{slug}", response_class=HTMLResponse, name="project_overview")
    async def project_overview(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "overview")

    @app.get("/projects/{slug}/board", response_class=HTMLResponse, name="project_board")
    async def project_board(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "board")

    @app.get("/projects/{slug}/plan", name="project_plan")
    async def project_plan(request: Request, slug: str) -> RedirectResponse:
        # back-compat alias: the "Plan" tab links to /board now
        return RedirectResponse(request.url_for("project_board", slug=slug), status_code=308)

    @app.get("/projects/{slug}/timeline", response_class=HTMLResponse, name="project_timeline")
    async def project_timeline(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "timeline")

    @app.get("/projects/{slug}/view", response_class=HTMLResponse, name="project_view")
    async def project_view(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "view_mode")

    @app.get("/projects/{slug}/people", response_class=HTMLResponse, name="project_people")
    async def project_people(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "people")

    @app.get("/projects/{slug}/dictionary", response_class=HTMLResponse, name="project_dictionary")
    async def project_dictionary(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "dictionary")

    @app.get("/projects/{slug}/documents", response_class=HTMLResponse, name="project_documents")
    async def project_documents(request: Request, slug: str) -> HTMLResponse:
        return await render_project_page(request, slug, "documents")

    @app.get("/projects/{slug}/people-access", name="project_people_access")
    async def project_people_access_legacy(request: Request, slug: str) -> RedirectResponse:
        # back-compat redirect for any saved bookmarks / addendum links
        return RedirectResponse(request.url_for("project_people", slug=slug), status_code=308)

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
        return_to: str = Form(""),
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
        return redirect_to(milestone_return_url(request, slug, return_to), "Milestone added.", "success")

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
        return_to: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        milestone = find_item(loaded.project.milestones, milestone_id)
        milestone.title = title.strip()
        milestone.owner_person_id = owner_person_id or None
        milestone.target_date = parse_date(target_date_value)
        try:
            milestone.status = MilestoneStatus(status)
        except ValueError:
            milestone.status = MilestoneStatus.PLANNED
        milestone.notes = notes.strip()
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Updated milestone '{milestone.title}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(milestone_return_url(request, slug, return_to), "Milestone updated.", "success")

    @app.post("/projects/{slug}/milestones/{milestone_id}/delete", name="milestone_delete")
    async def delete_milestone(
        request: Request,
        slug: str,
        milestone_id: str,
        change_note: str = Form(""),
        return_to: str = Form(""),
    ) -> RedirectResponse:
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
        return redirect_to(milestone_return_url(request, slug, return_to), "Milestone deleted.", "success")

    @app.post("/projects/{slug}/tasks", name="task_create")
    async def create_task(request: Request, slug: str) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        form = await request.form()
        title = str(form.get("title", "")).strip()
        column = str(form.get("column", loaded.project.board_columns[0]))
        if str(form.get("blocked", "")) == "on":
            column = "Blocked"
        task = Task(
            title=title,
            description=str(form.get("description", "")).strip(),
            column=column,
            assignee_ids=form.getlist("assignee_ids"),
            start_date=parse_date(str(form.get("start_date", ""))),
            due_date=parse_date(str(form.get("due_date", ""))),
            milestone_id=str(form.get("milestone_id", "")) or None,
            priority=str(form.get("priority", Priority.MEDIUM.value)),
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
        new_column = str(form.get("column", task.column))
        if str(form.get("blocked", "")) == "on":
            new_column = "Blocked"
        task.column = new_column
        task.assignee_ids = [str(item) for item in form.getlist("assignee_ids")]
        task.start_date = parse_date(str(form.get("start_date", "")))
        task.due_date = parse_date(str(form.get("due_date", "")))
        task.milestone_id = str(form.get("milestone_id", "")) or None
        task.priority = str(form.get("priority", Priority.MEDIUM.value))
        task.notes = str(form.get("notes", "")).strip()
        task.subtasks = parse_subtasks_payload(str(form.get("subtasks_json", "")), task.subtasks)
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
        return redirect_to(request.url_for("project_people", slug=slug), "Person added.", "success")

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
        return redirect_to(request.url_for("project_people", slug=slug), "Person updated.", "success")

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
                request.url_for("project_people", slug=slug),
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
        return redirect_to(request.url_for("project_people", slug=slug), "Person deleted.", "success")

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
        return redirect_to(request.url_for("project_dictionary", slug=slug), "Access category added.", "success")

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
        return redirect_to(request.url_for("project_dictionary", slug=slug), "Access category updated.", "success")

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
                request.url_for("project_dictionary", slug=slug),
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
        return redirect_to(request.url_for("project_dictionary", slug=slug), "Access category deleted.", "success")

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
        return redirect_to(request.url_for("project_dictionary", slug=slug), "Access link added.", "success")

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
        return redirect_to(request.url_for("project_dictionary", slug=slug), "Access link updated.", "success")

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
        return redirect_to(request.url_for("project_dictionary", slug=slug), "Access link deleted.", "success")

    @app.post("/projects/{slug}/dictionary", name="dictionary_create")
    async def create_dictionary_entry(
        request: Request,
        slug: str,
        key: str = Form(...),
        label: str = Form(""),
        value: str = Form(""),
        notes: str = Form(""),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        clean_key = key.strip()
        if not _is_valid_dictionary_key(clean_key):
            return redirect_to(
                request.url_for("project_dictionary", slug=slug),
                "Dictionary keys must start with a letter or underscore and use only letters, numbers, and underscores.",
                "error",
            )
        if any(entry.key == clean_key for entry in loaded.project.dictionary):
            return redirect_to(
                request.url_for("project_dictionary", slug=slug),
                f"A dictionary entry with key '{clean_key}' already exists.",
                "error",
            )
        loaded.project.dictionary.append(
            DictionaryEntry(key=clean_key, label=label.strip(), value=value.strip(), notes=notes.strip())
        )
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Added dictionary entry '{clean_key}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_dictionary", slug=slug), "Dictionary entry added.", "success")

    @app.post("/projects/{slug}/dictionary/{entry_id}", name="dictionary_update")
    async def update_dictionary_entry(
        request: Request,
        slug: str,
        entry_id: str,
        key: str = Form(...),
        label: str = Form(""),
        value: str = Form(""),
        notes: str = Form(""),
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        entry = find_item(loaded.project.dictionary, entry_id)
        clean_key = key.strip()
        if not _is_valid_dictionary_key(clean_key):
            return redirect_to(
                request.url_for("project_dictionary", slug=slug),
                "Dictionary keys must start with a letter or underscore and use only letters, numbers, and underscores.",
                "error",
            )
        if clean_key != entry.key and any(other.key == clean_key for other in loaded.project.dictionary if other.id != entry_id):
            return redirect_to(
                request.url_for("project_dictionary", slug=slug),
                f"A dictionary entry with key '{clean_key}' already exists.",
                "error",
            )
        entry.key = clean_key
        entry.label = label.strip()
        entry.value = value.strip()
        entry.notes = notes.strip()
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or f"Updated dictionary entry '{clean_key}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_dictionary", slug=slug), "Dictionary entry updated.", "success")

    @app.post("/projects/{slug}/dictionary/{entry_id}/delete", name="dictionary_delete")
    async def delete_dictionary_entry(
        request: Request,
        slug: str,
        entry_id: str,
        change_note: str = Form(""),
    ) -> RedirectResponse:
        loaded = safe_load_project(storage, slug)
        loaded.project.dictionary = [item for item in loaded.project.dictionary if item.id != entry_id]
        storage.save_project(
            loaded.project,
            loaded.sections,
            note=change_note.strip() or "Deleted dictionary entry",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )
        return redirect_to(request.url_for("project_dictionary", slug=slug), "Dictionary entry deleted.", "success")

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
        # normalise CRLF → LF before storing so we don't reintroduce growing whitespace
        loaded.sections[section_name] = body.replace("\r\n", "\n").replace("\r", "\n")
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
        timeline_text = timeline_text.replace("\r\n", "\n").replace("\r", "\n")
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
            "blocked_tasks": [task for task in loaded.project.tasks if task.column == "Blocked"],
            "import_summary": loaded.import_summary,
            "validation_errors": loaded.validation_errors,
            "sync_notice": loaded.sync_notice,
            "tab_template": tab_template(active_tab),
            "export_mode": False,
            "present_mode": active_tab == "view_mode",
            "progress_pct": progress_pct(loaded.project),
            "prefill_key": request.query_params.get("prefill_key", ""),
        }
        if active_tab == "documents":
            context["document_views"] = build_project_document_views(storage, loaded.project)
        return render_template(request, "project.html", context)

    return app


def render_markdown(value: str) -> str:
    return markdown(value or "", extensions=["fenced_code", "tables", "sane_lists", "nl2br"])


def model_list_json(values: list[Any]) -> Any:
    """Jinja filter: serialize a list of Pydantic models as JSON for embedding in markup.

    `tojson` alone can't handle Pydantic v2 models; this dumps each via `model_dump`
    first. Returns a Markup-safe string so it isn't HTML-entity-escaped inside the
    `<script type="application/json">` block (mirrors Jinja's built-in `tojson`).
    """
    from markupsafe import Markup

    payload = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in values or []]
    # Match Jinja's htmlsafe_json_dumps escapes so the result is safe in attributes too.
    encoded = (
        json.dumps(payload)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("'", "\\u0027")
    )
    return Markup(encoded)


_DICT_KEY_RE = __import__("re").compile(r"^[A-Za-z_][\w]*$")


def _is_valid_dictionary_key(key: str) -> bool:
    return bool(key) and _DICT_KEY_RE.match(key) is not None


def milestone_return_url(request: Request, slug: str, return_to: str) -> str:
    """Pick the redirect target for milestone routes based on an opt-in form field.

    Default Summary keeps existing call sites unchanged; the Plan-tab Add Milestone
    form opts in by posting return_to=plan so the user stays on the Board.
    """
    if return_to == "plan":
        return str(request.url_for("project_board", slug=slug))
    return str(request.url_for("project_overview", slug=slug))


def parse_subtasks_payload(raw: str, existing: list[Subtask]) -> list[Subtask]:
    """Decode the hidden subtasks_json field into a normalized Subtask list.

    Reuses existing IDs so addendum diffs stay tight when a user only toggles or
    retitles. Blank titles are dropped silently — empty rows in the UI are not
    persisted.
    """
    raw = raw.strip()
    if not raw:
        return list(existing)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return list(existing)
    if not isinstance(payload, list):
        return list(existing)
    by_id = {sub.id: sub for sub in existing}
    new_list: list[Subtask] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title", "")).strip()
        if not title:
            continue
        sid = str(entry.get("id", "")).strip()
        prior = by_id.get(sid) if sid else None
        if not sid:
            sid = make_id("sub")
        new_list.append(Subtask(id=sid, title=title, done=bool(entry.get("done", prior.done if prior else False))))
    return new_list


def task_completion(task: Task) -> float:
    if task.column == "Done":
        return 1.0
    if not task.subtasks:
        return 0.0
    done = sum(1 for sub in task.subtasks if sub.done)
    return done / len(task.subtasks)


def progress_pct(project: Project) -> float:
    total = len(project.tasks)
    if not total:
        return 0.0
    return sum(task_completion(task) for task in project.tasks) / total


def days_blocked(addendums: list[Any], task_id: str, today: date) -> int | None:
    """How many days the task has been in the Blocked column.

    Walks history to find the most recent move TO Blocked. Falls back to
    the project's earliest addendum if we can't pinpoint the move.
    """
    if not addendums:
        return None
    for addendum in addendums:
        for line in addendum.summary or []:
            if "Blocked" in line and task_id[:8] in line:
                return max((today - addendum.created_at.date()).days, 0)
    return max((today - addendums[-1].created_at.date()).days, 0)


def render_template(request: Request, template_name: str, context: dict[str, Any]) -> HTMLResponse:
    templates: Jinja2Templates = request.app.state.templates
    storage: StorageService = request.app.state.storage
    sidebar_ctx = build_sidebar_context(storage, request, context)
    merged = {
        "request": request,
        "message": context.get("message", request.query_params.get("message", "")),
        "message_level": context.get("message_level", request.query_params.get("level", "info")),
        **sidebar_ctx,
    }
    merged.update(context)
    return templates.TemplateResponse(request, template_name, merged)


def build_sidebar_context(storage: StorageService, request: Request, page_context: dict[str, Any]) -> dict[str, Any]:
    """Sidebar + breadcrumb context shared across every page."""
    import os

    path = request.url.path
    active_nav = "dashboard"
    if path.startswith("/projects/new") or path == "/projects/new":
        active_nav = "new_project"
    elif path.startswith("/projects/"):
        active_nav = "project"
    elif path.startswith("/templates"):
        active_nav = "templates"
    elif path.startswith("/exports"):
        active_nav = "exports"
    elif path.startswith("/inbox"):
        active_nav = "inbox"
    elif path.startswith("/risks"):
        active_nav = "risks"

    risks_count = 0
    sidebar_projects: list[dict[str, Any]] = []
    for entry in storage.list_dashboard_projects(sort_by="recent_update", include_archived=False):
        sidebar_projects.append({"slug": entry.slug, "name": entry.name, "health": entry.health.value})
        if entry.health.value == "blocked":
            risks_count += 1
        risks_count += entry.roadblock_count

    # Match the Inbox page's "Last 24h · N" segmented-control count.
    inbox_cutoff = datetime.now() - timedelta(hours=24)
    inbox_count = sum(
        1
        for _, addendum in storage.list_recent_addendums(limit=50, include_archived=False)
        if addendum.created_at >= inbox_cutoff
    )

    breadcrumb_trail = build_breadcrumbs(active_nav, request, page_context)

    try:
        identity = os.getlogin().split(".")[0].split("_")[0].title()
    except OSError:
        identity = "You"

    active_project_slug = ""
    if active_nav == "project":
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            active_project_slug = parts[1]

    return {
        "active_nav": active_nav,
        "active_project_slug": active_project_slug,
        "inbox_count": inbox_count,
        "risks_count": risks_count,
        "sidebar_projects": sidebar_projects,
        "breadcrumb_trail": breadcrumb_trail,
        "identity": identity,
    }


def build_breadcrumbs(active_nav: str, request: Request, page_context: dict[str, Any]) -> list[dict[str, str]]:
    crumbs: list[dict[str, str]] = [{"label": "Workspace", "url": str(request.url_for("dashboard"))}]
    project = page_context.get("project")
    template_pages = {
        "dashboard": "Dashboard",
        "new_project": "New project",
        "templates": "Templates",
        "exports": "Exports",
        "inbox": "Inbox",
        "risks": "Risks & roadblocks",
    }
    if active_nav in template_pages:
        crumbs.append({"label": template_pages[active_nav], "url": ""})
    elif active_nav == "project" and project:
        # Workspace already points to the dashboard; the dropped "Projects"
        # crumb pointed there too, doubling up the same target.
        crumbs.append({"label": project.name, "url": ""})
    return crumbs


def build_portfolio_gantt(projects: list[Project], today: date) -> dict[str, Any]:
    dated_projects = [project for project in projects if project.start_date or project.end_date]
    if not dated_projects:
        return {"rows": [], "start": None, "end": None, "total_days": 0, "today_percent": None}

    starts = [project.start_date or project.end_date for project in dated_projects]
    ends = [project.end_date or project.start_date for project in dated_projects]
    chart_start = min(item for item in starts if item is not None)
    chart_end = max(item for item in ends if item is not None)
    total_days = max((chart_end - chart_start).days, 1)

    rows = []
    for project in dated_projects:
        start = project.start_date or project.end_date or chart_start
        end = project.end_date or project.start_date or start
        if end < start:
            start, end = end, start
        offset = ((start - chart_start).days / total_days) * 100
        width = max(((end - start).days / total_days) * 100, 2)
        offset = min(max(offset, 0), 100)
        width = min(width, 100 - offset)
        milestones = []
        for milestone in project.milestones:
            if milestone.target_date is None:
                continue
            milestones.append(
                {
                    "title": milestone.title,
                    "date": milestone.target_date,
                    "status": milestone.status.value,
                    "offset": min(max(((milestone.target_date - chart_start).days / total_days) * 100, 0), 100),
                }
            )
        owner_initials = []
        for person in project.people[:3]:
            parts = person.name.split()
            if not parts:
                continue
            initials = parts[0][:1] + (parts[1][:1] if len(parts) > 1 else "")
            owner_initials.append({"initials": initials.upper(), "name": person.name})
        rows.append(
            {
                "slug": project.slug,
                "name": project.name,
                "health": project.health.value,
                "status": project.status.value,
                "start": start,
                "end": end,
                "offset": offset,
                "width": width,
                "milestones": milestones,
                "progress_pct": progress_pct(project),
                "owners": owner_initials,
                "extra_owner_count": max(len(project.people) - 3, 0),
            }
        )

    today_percent = None
    if chart_start <= today <= chart_end:
        today_percent = ((today - chart_start).days / total_days) * 100

    # Build month-tick markers for the time axis
    axis_ticks: list[dict[str, Any]] = []
    cursor = date(chart_start.year, chart_start.month, 1)
    if cursor < chart_start:
        # advance to next month
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    while cursor <= chart_end:
        offset_pct = ((cursor - chart_start).days / total_days) * 100
        if 0 <= offset_pct <= 100:
            axis_ticks.append(
                {
                    "label": cursor.strftime("%b") if cursor.month != 1 else cursor.strftime("%b %Y"),
                    "offset": offset_pct,
                }
            )
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    return {
        "rows": rows,
        "start": chart_start,
        "end": chart_end,
        "total_days": total_days,
        "today_percent": today_percent,
        "axis_ticks": axis_ticks,
    }


BUILTIN_TAG_KEYS: frozenset[str] = frozenset(
    {
        "project_name",
        "project_description",
        "project_status",
        "project_health",
        "project_start_date",
        "project_end_date",
        "today",
        "people",
        "milestones",
    }
)


def serialize_document_template_fields(fields: list[DocumentTemplateField]) -> str:
    """Inverse of parse_document_template_fields — used to seed the textarea editor."""
    lines = []
    for field in fields:
        aliases = ",".join(field.aliases) if field.aliases else ""
        required = "required" if field.required else "optional"
        lines.append(
            f"{field.key}|{field.label}|{field.field_type.value}|{aliases}|{required}|{field.value}"
        )
    return "\n".join(lines)


def parse_document_template_fields(fields_text: str) -> list[DocumentTemplateField]:
    fields: list[DocumentTemplateField] = []
    for line in fields_text.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue
        parts = [part.strip() for part in clean_line.split("|")]
        key = parts[0] if parts else ""
        label = parts[1] if len(parts) > 1 and parts[1] else key.replace("_", " ").title()
        field_type = parts[2] if len(parts) > 2 and parts[2] else DocumentFieldType.STRING.value
        aliases = parts[3] if len(parts) > 3 else ""
        required = True
        if len(parts) > 4:
            required = parts[4].lower() not in {"optional", "false", "no", "0"}
        value = parts[5] if len(parts) > 5 else ""
        fields.append(
            DocumentTemplateField(
                key=slugify(key).replace("-", "_"),
                label=label,
                field_type=DocumentFieldType(field_type),
                aliases=aliases,
                required=required,
                value=value,
            )
        )
    return fields


def build_project_document_views(storage: StorageService, project: Project) -> list[dict[str, Any]]:
    """Per-template, per-project tag inspection — mirrors `build_render_context` priority.

    Resolution order matches storage.build_render_context: project.dictionary > template.fields[].value > built-in.
    """
    views: list[dict[str, Any]] = []
    dict_entries = {entry.key: entry for entry in project.dictionary if entry.key and entry.value.strip()}
    for template in storage.list_document_templates():
        docx_path = storage.document_template_docx_path(template)
        tags_found = inspect_docx_tags(docx_path) if docx_path else []
        field_keys = {field.key: field for field in template.fields}
        rows: list[dict[str, Any]] = []
        counts = {"declared": 0, "builtin": 0, "template_default": 0, "missing": 0}
        for tag in tags_found:
            if tag in dict_entries:
                rows.append({"tag": tag, "status": "declared", "source": dict_entries[tag].value})
                counts["declared"] += 1
            elif tag in BUILTIN_TAG_KEYS:
                rows.append({"tag": tag, "status": "builtin", "source": ""})
                counts["builtin"] += 1
            elif tag in field_keys and field_keys[tag].value.strip():
                rows.append({"tag": tag, "status": "template_default", "source": field_keys[tag].value})
                counts["template_default"] += 1
            else:
                rows.append({"tag": tag, "status": "missing", "source": ""})
                counts["missing"] += 1
        counts["total_non_builtin"] = counts["declared"] + counts["template_default"] + counts["missing"]
        views.append(
            {
                "template": template,
                "tag_rows": rows,
                "counts": counts,
                "has_docx": bool(docx_path),
            }
        )
    return views


def build_canonical_field_index(document_templates: list[Any]) -> list[dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for template in document_templates:
        for field in template.fields:
            entry = index.setdefault(
                field.key,
                {
                    "key": field.key,
                    "labels": set(),
                    "aliases": set(),
                    "documents": [],
                    "missing_count": 0,
                },
            )
            entry["labels"].add(field.label)
            entry["aliases"].update(field.aliases)
            entry["documents"].append(template.name)
            if field.required and not field.value.strip():
                entry["missing_count"] += 1
    return [
        {
            "key": key,
            "labels": sorted(value["labels"]),
            "aliases": sorted(value["aliases"]),
            "documents": sorted(value["documents"]),
            "missing_count": value["missing_count"],
        }
        for key, value in sorted(index.items())
    ]


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
        "people": "partials/project_people.html",
        "dictionary": "partials/project_dictionary.html",
        "documents": "partials/project_documents.html",
        "people_access": "partials/project_people.html",  # legacy alias
        "sections": "partials/project_section.html",
        "history": "partials/project_history.html",
    }
    return mapping[active_tab]


app = create_app()
