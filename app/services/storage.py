from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError

from app.config import AppConfig
from app.models import (
    AccessCategory,
    Addendum,
    DashboardProject,
    DocumentTemplate,
    DocumentTemplateField,
    HealthStatus,
    Project,
    ProjectLoadResult,
    ProjectSnapshot,
    ProjectTemplate,
    SectionName,
    SyncHealth,
    SyncState,
    make_id,
)
from app.services.history import build_addendum, render_addendum_markdown
from app.services.mermaid import import_timeline, render_timeline
from app.utils import dumps_pretty, now_stamp, sha1_text, slugify


SECTION_NAMES: tuple[SectionName, ...] = ("content", "change_requests", "roadblocks", "notes")


class StorageService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.config.projects_dir.mkdir(parents=True, exist_ok=True)
        self.config.exports_dir.mkdir(parents=True, exist_ok=True)
        self.config.project_templates_dir.mkdir(parents=True, exist_ok=True)
        self.config.document_templates_dir.mkdir(parents=True, exist_ok=True)

    def list_dashboard_projects(
        self,
        search: str = "",
        health: str = "",
        sort_by: str = "recent_update",
        include_archived: bool = False,
    ) -> list[DashboardProject]:
        results: list[DashboardProject] = []
        for project_dir in sorted(self.config.projects_dir.glob("*")):
            if not project_dir.is_dir():
                continue
            loaded = self.load_project(project_dir.name)
            entry = self._dashboard_entry(loaded)
            if entry.archived and not include_archived:
                continue
            if search and search.lower() not in self._search_blob(loaded.project):
                continue
            if health and entry.health.value != health:
                continue
            results.append(entry)
        return self._sort_dashboard_projects(results, sort_by)

    def list_recent_addendums(self, limit: int = 10, include_archived: bool = False) -> list[tuple[str, Addendum]]:
        items: list[tuple[str, Addendum]] = []
        for project_dir in self.config.projects_dir.glob("*"):
            if not project_dir.is_dir():
                continue
            if not include_archived:
                loaded = self.load_project(project_dir.name)
                if loaded.project.archived:
                    continue
            for addendum in self._read_history(project_dir)[:limit]:
                items.append((project_dir.name, addendum))
        items.sort(key=lambda item: item[1].created_at, reverse=True)
        return items[:limit]

    def create_project(self, name: str, description: str = "", start_date: date | None = None, end_date: date | None = None) -> Project:
        slug = self._unique_slug(slugify(name))
        project = Project(
            slug=slug,
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date,
            access_links=[AccessCategory(name=item) for item in self.config.default_access_categories],
            board_columns=list(self.config.default_board_columns),
        )
        sections = {section: "" for section in SECTION_NAMES}
        self.save_project(project, sections, note="Project created", actor="web")
        return project

    def create_project_from_template(
        self,
        template_slug: str,
        name: str,
        description: str = "",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Project:
        template = self.load_project_template(template_slug)
        project = template.snapshot.project.model_copy(deep=True)
        project.id = make_id("project")
        project.slug = self._unique_slug(slugify(name))
        project.name = name
        project.description = description or project.description
        project.start_date = start_date or project.start_date
        project.end_date = end_date or project.end_date
        project.archived = False
        project.archived_at = None
        project.sync_state = SyncState()
        self.save_project(
            project,
            template.snapshot.sections.copy(),
            note=f"Project created from template '{template.name}'",
            actor="template",
            timeline_text=render_timeline(project),
        )
        return project

    def list_project_templates(self) -> list[ProjectTemplate]:
        templates = []
        for path in sorted(self.config.project_templates_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            templates.append(ProjectTemplate.model_validate(payload))
        templates.sort(key=lambda item: item.name.lower())
        return templates

    def load_project_template(self, slug: str) -> ProjectTemplate:
        path = self.config.project_templates_dir / f"{slug}.json"
        if not path.exists():
            raise FileNotFoundError(slug)
        return ProjectTemplate.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def create_project_template_from_project(self, project_slug: str, name: str, description: str = "") -> ProjectTemplate:
        loaded = self.load_project(project_slug)
        slug = self._unique_template_slug(slugify(name), self.config.project_templates_dir)
        template = ProjectTemplate(
            slug=slug,
            name=name,
            description=description,
            snapshot=ProjectSnapshot(
                project=loaded.project.model_copy(deep=True),
                sections=loaded.sections.copy(),
                timeline_text=loaded.timeline_text,
            ),
        )
        (self.config.project_templates_dir / f"{slug}.json").write_text(
            dumps_pretty(template.model_dump(mode="json")),
            encoding="utf-8",
        )
        return template

    def list_document_templates(self) -> list[DocumentTemplate]:
        templates = []
        for path in sorted(self.config.document_templates_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            templates.append(DocumentTemplate.model_validate(payload))
        templates.sort(key=lambda item: item.name.lower())
        return templates

    def create_document_template(self, name: str, description: str, fields: list[DocumentTemplateField]) -> DocumentTemplate:
        slug = self._unique_template_slug(slugify(name), self.config.document_templates_dir)
        template = DocumentTemplate(slug=slug, name=name, description=description, fields=fields)
        self.save_document_template(template)
        return template

    def save_document_template(self, template: DocumentTemplate) -> None:
        (self.config.document_templates_dir / f"{template.slug}.json").write_text(
            dumps_pretty(template.model_dump(mode="json")),
            encoding="utf-8",
        )

    def load_document_template(self, slug: str) -> DocumentTemplate:
        path = self.config.document_templates_dir / f"{slug}.json"
        if not path.exists():
            raise FileNotFoundError(slug)
        return DocumentTemplate.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def delete_document_template(self, slug: str) -> None:
        json_path = self.config.document_templates_dir / f"{slug}.json"
        if json_path.exists():
            json_path.unlink()
        assets_dir = self.config.document_templates_dir / slug
        if assets_dir.exists():
            shutil.rmtree(assets_dir)

    def document_template_assets_dir(self, slug: str) -> Path:
        return self.config.document_templates_dir / slug

    def document_template_docx_path(self, template: DocumentTemplate) -> Path | None:
        if not template.docx_filename:
            return None
        path = self.document_template_assets_dir(template.slug) / template.docx_filename
        return path if path.exists() else None

    def save_document_template_file(self, slug: str, filename: str, data: bytes) -> DocumentTemplate:
        template = self.load_document_template(slug)
        assets_dir = self.document_template_assets_dir(slug)
        assets_dir.mkdir(parents=True, exist_ok=True)
        # remove any previous .docx so the directory holds a single template file
        for existing in assets_dir.glob("*.docx"):
            existing.unlink()
        safe_name = filename.replace("\\", "_").replace("/", "_") or "template.docx"
        if not safe_name.lower().endswith(".docx"):
            safe_name += ".docx"
        (assets_dir / safe_name).write_bytes(data)
        template.docx_filename = safe_name
        self.save_document_template(template)
        return template

    def remove_document_template_file(self, slug: str) -> DocumentTemplate:
        template = self.load_document_template(slug)
        assets_dir = self.document_template_assets_dir(slug)
        if assets_dir.exists():
            for existing in assets_dir.glob("*.docx"):
                existing.unlink()
        template.docx_filename = None
        self.save_document_template(template)
        return template

    def render_document_template(self, slug: str, project_slug: str) -> tuple[bytes, str]:
        from io import BytesIO

        try:
            from docxtpl import DocxTemplate
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "Install the 'docx' optional dependency: python -m pip install -e \".[docx]\""
            ) from exc

        template = self.load_document_template(slug)
        docx_path = self.document_template_docx_path(template)
        if docx_path is None:
            raise FileNotFoundError("Upload a .docx file before rendering this template.")

        loaded = self.load_project(project_slug)
        context = build_render_context(template, loaded.project)

        doc = DocxTemplate(str(docx_path))
        doc.render(context)
        buffer = BytesIO()
        doc.save(buffer)

        base = template.slug
        return buffer.getvalue(), f"{base}__{loaded.project.slug}.docx"

    def archive_project(self, slug: str, note: str = "") -> Addendum:
        loaded = self.load_project(slug)
        loaded.project.archived = True
        loaded.project.archived_at = datetime.now()
        return self.save_project(
            loaded.project,
            loaded.sections,
            note=note.strip() or f"Archived project '{loaded.project.name}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )

    def unarchive_project(self, slug: str, note: str = "") -> Addendum:
        loaded = self.load_project(slug)
        loaded.project.archived = False
        loaded.project.archived_at = None
        return self.save_project(
            loaded.project,
            loaded.sections,
            note=note.strip() or f"Unarchived project '{loaded.project.name}'",
            preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned,
        )

    def delete_project(self, slug: str) -> None:
        project_dir = self._project_dir(slug).resolve()
        projects_root = self.config.projects_dir.resolve()
        if not project_dir.exists():
            raise FileNotFoundError(slug)
        if project_dir.parent != projects_root:
            raise ValueError("Refusing to delete outside the projects directory.")
        shutil.rmtree(project_dir)

    def duplicate_project(self, slug: str, new_name: str, note: str = "") -> Project:
        loaded = self.load_project(slug)
        clean_name = new_name.strip() or f"{loaded.project.name} Copy"
        duplicated = loaded.project.model_copy(deep=True)
        duplicated.id = make_id("project")
        duplicated.slug = self._unique_slug(slugify(clean_name))
        duplicated.name = clean_name
        duplicated.archived = False
        duplicated.archived_at = None
        duplicated.sync_state = SyncState()

        self._copy_logo_asset(loaded.project, duplicated)
        self.save_project(
            duplicated,
            loaded.sections.copy(),
            note=note.strip() or f"Duplicated from '{loaded.project.name}'",
            actor="duplicate",
            timeline_text=render_timeline(duplicated),
        )
        return duplicated

    def load_project(self, slug: str) -> ProjectLoadResult:
        project_dir = self._project_dir(slug)
        if not project_dir.exists():
            raise FileNotFoundError(slug)
        project_path = project_dir / "project.json"
        raw_json = project_path.read_text(encoding="utf-8") if project_path.exists() else ""
        fallback_snapshot = self._latest_snapshot(project_dir)
        if not raw_json and fallback_snapshot is None:
            raise FileNotFoundError(slug)
        validation_errors: list[str] = []

        try:
            stored_project = Project.model_validate_json(raw_json)
        except (ValidationError, json.JSONDecodeError) as exc:
            if fallback_snapshot is None:
                raise
            stored_project = fallback_snapshot.project.model_copy(deep=True)
            validation_errors.append(f"Invalid project.json detected. Loaded last good snapshot instead: {exc}")
        project = stored_project.model_copy(deep=True)

        sections = {section: self._section_path(project_dir, section).read_text(encoding="utf-8") if self._section_path(project_dir, section).exists() else "" for section in SECTION_NAMES}
        timeline_path = project_dir / "timeline.mmd"
        timeline_text = timeline_path.read_text(encoding="utf-8") if timeline_path.exists() else render_timeline(project)

        sync_notice_parts: list[str] = []
        import_summary: list[str] = []
        current_project_hash = self._project_signature(stored_project)
        project_changed = bool(stored_project.sync_state.project_hash and stored_project.sync_state.project_hash != current_project_hash)
        if project_changed:
            sync_notice_parts.append("project.json changed outside the app")

        section_changes: list[str] = []
        for section_name, section_text in sections.items():
            current_hash = sha1_text(section_text)
            expected_hash = project.sync_state.section_hashes.get(section_name, "")
            if expected_hash and expected_hash != current_hash:
                change_note = f"{section_name}.md changed outside the app"
                sync_notice_parts.append(change_note)
                section_changes.append(change_note)

        current_timeline_hash = sha1_text(timeline_text)
        timeline_changed = bool(project.sync_state.timeline_hash and project.sync_state.timeline_hash != current_timeline_hash)
        if timeline_changed:
            sync_notice_parts.append("timeline.mmd changed outside the app")

        imported_project, imported, mermaid_errors, supported = import_timeline(project.model_copy(deep=True), timeline_text)
        if imported and timeline_changed:
            import_summary.extend(imported)
        if mermaid_errors:
            validation_errors.extend(mermaid_errors)
        project = imported_project
        project.sync_state.project_hash = current_project_hash
        project.sync_state.section_hashes = {section: sha1_text(text) for section, text in sections.items()}
        project.sync_state.timeline_hash = current_timeline_hash
        project.sync_state.external_changes = sorted(set(sync_notice_parts))
        project.sync_state.validation_errors = validation_errors.copy()
        project.sync_state.health = self._sync_health(sync_notice_parts, validation_errors, supported)
        project.sync_state.timeline_is_app_owned = supported

        return ProjectLoadResult(
            project=project,
            sections=sections,
            timeline_text=timeline_text,
            addendums=self._read_history(project_dir),
            sync_notice="; ".join(sorted(set(sync_notice_parts))),
            validation_errors=validation_errors,
            import_summary=import_summary,
        )

    def save_project(
        self,
        project: Project,
        sections: dict[SectionName, str],
        note: str = "",
        actor: str = "web",
        timeline_text: str | None = None,
        preserve_timeline: bool = False,
    ) -> Addendum:
        project_dir = self._project_dir(project.slug)
        history_dir = project_dir / "history"
        project_dir.mkdir(parents=True, exist_ok=True)
        history_dir.mkdir(parents=True, exist_ok=True)
        before = self._latest_snapshot(project_dir)

        for section_name in SECTION_NAMES:
            self._section_path(project_dir, section_name).write_text(sections.get(section_name, ""), encoding="utf-8")

        timeline_path = project_dir / "timeline.mmd"
        current_timeline = timeline_path.read_text(encoding="utf-8") if timeline_path.exists() else ""
        final_timeline = current_timeline if preserve_timeline and current_timeline else timeline_text or render_timeline(project)
        timeline_path.write_text(final_timeline, encoding="utf-8")

        project.sync_state.project_hash = ""
        project.sync_state.timeline_hash = sha1_text(final_timeline)
        project.sync_state.section_hashes = {section: sha1_text(sections.get(section, "")) for section in SECTION_NAMES}
        project.sync_state.external_changes = []
        project.sync_state.validation_errors = []
        project.sync_state.health = SyncHealth.SYNCED
        project.sync_state.last_app_save_at = datetime.now()
        project.sync_state.timeline_is_app_owned = not preserve_timeline

        project_path = project_dir / "project.json"
        project.sync_state.project_hash = self._project_signature(project)
        project_json = dumps_pretty(project.model_dump(mode="json"))
        project_path.write_text(project_json, encoding="utf-8")

        snapshot = ProjectSnapshot(project=project.model_copy(deep=True), sections=sections.copy(), timeline_text=final_timeline)
        entry_id = now_stamp()
        addendum = build_addendum(entry_id, datetime.now(), note, actor, before, snapshot)
        (history_dir / f"{entry_id}.json").write_text(
            dumps_pretty(addendum.model_dump(mode="json")),
            encoding="utf-8",
        )
        (history_dir / f"{entry_id}.md").write_text(render_addendum_markdown(addendum), encoding="utf-8")
        return addendum

    def restore_history(self, slug: str, addendum_id: str, note: str = "") -> Addendum:
        project_dir = self._project_dir(slug)
        addendum_path = project_dir / "history" / f"{addendum_id}.json"
        payload = json.loads(addendum_path.read_text(encoding="utf-8"))
        addendum = Addendum.model_validate(payload)
        return self.save_project(
            addendum.snapshot.project,
            addendum.snapshot.sections,
            note=note or f"Restored snapshot {addendum_id}",
            actor="restore",
            timeline_text=addendum.snapshot.timeline_text,
        )

    def resolve_logo_file(self, project: Project) -> Path | None:
        if not project.logo_path:
            return None
        asset_path = Path(project.logo_path)
        if asset_path.is_absolute():
            return None
        project_dir = self._project_dir(project.slug).resolve()
        candidate = (project_dir / asset_path).resolve()
        if candidate.parent != project_dir and project_dir not in candidate.parents:
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate

    def _project_dir(self, slug: str) -> Path:
        return self.config.projects_dir / slug

    def _section_path(self, project_dir: Path, section: SectionName) -> Path:
        return project_dir / f"{section}.md"

    def _unique_slug(self, slug: str) -> str:
        candidate = slug
        index = 2
        while self._project_dir(candidate).exists():
            candidate = f"{slug}-{index}"
            index += 1
        return candidate

    def _unique_template_slug(self, slug: str, directory: Path) -> str:
        candidate = slug
        index = 2
        while (directory / f"{candidate}.json").exists():
            candidate = f"{slug}-{index}"
            index += 1
        return candidate

    def _latest_snapshot(self, project_dir: Path) -> ProjectSnapshot | None:
        history = self._read_history(project_dir)
        if not history:
            return None
        return history[0].snapshot

    def _read_history(self, project_dir: Path) -> list[Addendum]:
        history_dir = project_dir / "history"
        if not history_dir.exists():
            return []
        entries: list[Addendum] = []
        for path in sorted(history_dir.glob("*.json"), reverse=True):
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries.append(Addendum.model_validate(payload))
        return entries

    def _sync_health(self, changes: list[str], validation_errors: list[str], supported: bool) -> SyncHealth:
        if validation_errors:
            return SyncHealth.INVALID
        if not supported:
            return SyncHealth.UNSUPPORTED
        if changes:
            return SyncHealth.EXTERNAL_CHANGES
        return SyncHealth.SYNCED

    def _project_signature(self, project: Project) -> str:
        project_copy = project.model_copy(deep=True)
        project_copy.sync_state.project_hash = ""
        return sha1_text(dumps_pretty(project_copy.model_dump(mode="json")))

    def _dashboard_entry(self, loaded: ProjectLoadResult) -> DashboardProject:
        project = loaded.project
        next_milestone = next(
            (
                milestone
                for milestone in sorted(
                    [item for item in project.milestones if item.target_date],
                    key=lambda item: item.target_date or date.max,
                )
                if milestone.status != "complete"
            ),
            None,
        )
        roadblock_count = sum(1 for task in project.tasks if task.column == "Blocked")
        recent_at = loaded.addendums[0].created_at if loaded.addendums else None
        return DashboardProject(
            slug=project.slug,
            name=project.name,
            description=project.description,
            logo_path=project.logo_path,
            has_logo=self.resolve_logo_file(project) is not None,
            health=project.health,
            status=project.status,
            start_date=project.start_date,
            end_date=project.end_date,
            archived=project.archived,
            owner_names=[person.name for person in project.people[:3]],
            next_milestone=next_milestone,
            roadblock_count=roadblock_count,
            recent_addendum_at=recent_at,
        )

    def _search_blob(self, project: Project) -> str:
        parts = [project.name, project.description]
        for person in project.people:
            parts.extend([person.name, person.email, person.role])
        return " ".join(part.lower() for part in parts if part)

    def _sort_dashboard_projects(self, projects: list[DashboardProject], sort_by: str) -> list[DashboardProject]:
        items = list(projects)
        if sort_by == "name":
            items.sort(key=lambda item: item.name.lower())
            return items
        if sort_by == "end_date":
            items.sort(key=lambda item: (item.end_date is None, item.end_date or date.max, item.name.lower()))
            return items
        if sort_by == "next_milestone":
            items.sort(
                key=lambda item: (
                    item.next_milestone is None,
                    item.next_milestone.target_date if item.next_milestone and item.next_milestone.target_date else date.max,
                    item.name.lower(),
                )
            )
            return items
        items.sort(key=lambda item: item.name.lower())
        items.sort(key=lambda item: item.recent_addendum_at or datetime.min, reverse=True)
        return items

    def _copy_logo_asset(self, source: Project, target: Project) -> None:
        if not source.logo_path:
            target.logo_path = None
            return
        target.logo_path = source.logo_path
        source_logo = self.resolve_logo_file(source)
        if source_logo is None:
            return
        target_path = self._project_dir(target.slug) / source.logo_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_logo, target_path)


DOCX_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][\w]*)(?:\.[\w]+)*\s*(?:\|[^}]*)?\s*\}\}")
DOCX_FOR_RE = re.compile(r"\{%\s*for\s+\w+\s+in\s+([A-Za-z_][\w]*)\s*%\}")


def inspect_docx_tags(docx_path: Path) -> list[str]:
    """Return the unique top-level Jinja variable names referenced inside a .docx.

    Captures both `{{ key }}` substitutions and the iterable name in `{% for x in items %}` loops.
    Loop-bound names (`x`) are excluded.
    """
    if not docx_path.exists():
        return []
    found: set[str] = set()
    loop_vars: set[str] = set()
    try:
        with zipfile.ZipFile(docx_path) as zf:
            for name in zf.namelist():
                if not name.endswith(".xml"):
                    continue
                try:
                    text = zf.read(name).decode("utf-8", errors="ignore")
                except KeyError:
                    continue
                # Word can split a placeholder across multiple <w:t> runs; strip XML tags first.
                clean = re.sub(r"<[^>]+>", "", text)
                for match in DOCX_VAR_RE.finditer(clean):
                    found.add(match.group(1))
                for match in re.finditer(r"\{%\s*for\s+(\w+)\s+in\s+([A-Za-z_][\w]*)\s*%\}", clean):
                    loop_vars.add(match.group(1))
                    found.add(match.group(2))
    except zipfile.BadZipFile:
        return []
    return sorted(found - loop_vars)


def build_render_context(template: DocumentTemplate, project: Project) -> dict[str, object]:
    """Context dict for docxtpl rendering — fields first, then project metadata as fallback."""
    today = date.today()
    context: dict[str, object] = {
        "project_name": project.name,
        "project_description": project.description,
        "project_status": project.status.value,
        "project_health": project.health.value,
        "project_start_date": project.start_date.isoformat() if project.start_date else "",
        "project_end_date": project.end_date.isoformat() if project.end_date else "",
        "today": today.isoformat(),
        "people": [
            {"name": p.name, "email": p.email, "role": p.role}
            for p in project.people
        ],
        "milestones": [
            {
                "title": m.title,
                "status": m.status.value,
                "target_date": m.target_date.isoformat() if m.target_date else "",
            }
            for m in project.milestones
        ],
    }
    for field in template.fields:
        context[field.key] = field.value
    return context
