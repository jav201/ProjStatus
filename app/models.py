from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HealthStatus(StrEnum):
    ON_TRACK = "on-track"
    AT_RISK = "at-risk"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    PLANNED = "planned"
    HOLD = "hold"
    COMPLETE = "complete"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MilestoneStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETE = "complete"
    BLOCKED = "blocked"


class SyncHealth(StrEnum):
    SYNCED = "synced"
    EXTERNAL_CHANGES = "external_changes"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


class Person(BaseModel):
    id: str = Field(default_factory=lambda: make_id("person"))
    name: str
    email: str
    role: str


class AccessLink(BaseModel):
    id: str = Field(default_factory=lambda: make_id("link"))
    label: str
    url: str
    notes: str = ""
    owner_person_id: str | None = None


class AccessCategory(BaseModel):
    id: str = Field(default_factory=lambda: make_id("cat"))
    name: str
    links: list[AccessLink] = Field(default_factory=list)


class Milestone(BaseModel):
    id: str = Field(default_factory=lambda: make_id("milestone"))
    title: str
    owner_person_id: str | None = None
    target_date: date | None = None
    status: MilestoneStatus = MilestoneStatus.PLANNED
    notes: str = ""


class Task(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: make_id("task"))
    title: str
    description: str = ""
    column: str = "Backlog"
    assignee_ids: list[str] = Field(default_factory=list)
    start_date: date | None = None
    due_date: date | None = None
    milestone_id: str | None = None
    priority: Priority = Priority.MEDIUM
    notes: str = ""

    @field_validator("assignee_ids", mode="before")
    @classmethod
    def normalize_assignees(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item for item in value.split(",") if item]
        return list(value)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_blocked(cls, data: object) -> object:
        if isinstance(data, dict) and data.pop("blocked", False) and data.get("column") not in ("Blocked", "Done"):
            data["column"] = "Blocked"
        return data

    @property
    def blocked(self) -> bool:
        return self.column == "Blocked"


class SyncState(BaseModel):
    health: SyncHealth = SyncHealth.SYNCED
    project_hash: str = ""
    timeline_hash: str = ""
    section_hashes: dict[str, str] = Field(default_factory=dict)
    external_changes: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    last_app_save_at: datetime | None = None
    timeline_is_app_owned: bool = True


class Project(BaseModel):
    id: str = Field(default_factory=lambda: make_id("project"))
    slug: str
    name: str
    description: str = ""
    logo_path: str | None = None
    health: HealthStatus = HealthStatus.ON_TRACK
    status: ProjectStatus = ProjectStatus.ACTIVE
    start_date: date | None = None
    end_date: date | None = None
    archived: bool = False
    archived_at: datetime | None = None
    people: list[Person] = Field(default_factory=list)
    access_links: list[AccessCategory] = Field(default_factory=list)
    milestones: list[Milestone] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    board_columns: list[str] = Field(default_factory=lambda: ["Backlog", "In Progress", "Blocked", "Done"])
    sync_state: SyncState = Field(default_factory=SyncState)


SectionName = Literal["content", "change_requests", "roadblocks", "notes"]


class ProjectSnapshot(BaseModel):
    project: Project
    sections: dict[SectionName, str]
    timeline_text: str


class ProjectTemplate(BaseModel):
    slug: str
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    snapshot: ProjectSnapshot


class DocumentFieldType(StrEnum):
    STRING = "string"
    EXCEL_TABLE = "excel_table"
    EXCEL_CELL = "excel_cell"


class DocumentTemplateField(BaseModel):
    key: str
    label: str
    field_type: DocumentFieldType = DocumentFieldType.STRING
    required: bool = True
    aliases: list[str] = Field(default_factory=list)
    value: str = ""

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return list(value)


class DocumentTemplate(BaseModel):
    slug: str
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    fields: list[DocumentTemplateField] = Field(default_factory=list)
    docx_filename: str | None = None

    @property
    def required_count(self) -> int:
        return sum(1 for field in self.fields if field.required)

    @property
    def completed_required_count(self) -> int:
        return sum(1 for field in self.fields if field.required and field.value.strip())

    @property
    def completion_percent(self) -> int:
        if self.required_count == 0:
            return 100
        return round((self.completed_required_count / self.required_count) * 100)

    @property
    def missing_fields(self) -> list[DocumentTemplateField]:
        return [field for field in self.fields if field.required and not field.value.strip()]


class Addendum(BaseModel):
    id: str
    created_at: datetime
    note: str = ""
    actor: str = "web"
    changed_files: list[str] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)
    diffs: dict[str, str] = Field(default_factory=dict)
    snapshot: ProjectSnapshot


class ProjectLoadResult(BaseModel):
    project: Project
    sections: dict[SectionName, str]
    timeline_text: str
    addendums: list[Addendum] = Field(default_factory=list)
    sync_notice: str = ""
    validation_errors: list[str] = Field(default_factory=list)
    import_summary: list[str] = Field(default_factory=list)


class DashboardProject(BaseModel):
    slug: str
    name: str
    description: str = ""
    logo_path: str | None = None
    has_logo: bool = False
    health: HealthStatus
    status: ProjectStatus
    start_date: date | None = None
    end_date: date | None = None
    archived: bool = False
    owner_names: list[str] = Field(default_factory=list)
    next_milestone: Milestone | None = None
    roadblock_count: int = 0
    recent_addendum_at: datetime | None = None


class ExportFormat(StrEnum):
    HTML = "html"
    PNG = "png"
    PPTX = "pptx"


class ExportRequest(BaseModel):
    project_slugs: list[str]
    formats: list[ExportFormat]


class ExportResult(BaseModel):
    format: ExportFormat
    output_path: str
    success: bool
    message: str = ""
