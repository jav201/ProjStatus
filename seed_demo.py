"""Seed demo projects so the UI is populated for design review."""
from datetime import date, timedelta
from pathlib import Path

from app.config import AppConfig
from app.models import (
    AccessCategory,
    AccessLink,
    DocumentFieldType,
    DocumentTemplate,
    DocumentTemplateField,
    HealthStatus,
    Milestone,
    MilestoneStatus,
    Person,
    Priority,
    Project,
    ProjectStatus,
    Task,
)
from app.services.storage import StorageService


def main() -> None:
    config = AppConfig.from_root(Path(__file__).parent)
    storage = StorageService(config)
    today = date.today()

    rfq = Project(
        slug="rfq-line-12",
        name="RFQ Line 12 Automation",
        description="Track engineering, sourcing, and supplier-quote readiness for the new robotic line.",
        health=HealthStatus.AT_RISK,
        status=ProjectStatus.ACTIVE,
        start_date=today - timedelta(days=20),
        end_date=today + timedelta(days=70),
        people=[
            Person(name="Ana Pereira", email="ana@example.com", role="Project lead"),
            Person(name="Luis Romero", email="luis@example.com", role="Sourcing"),
            Person(name="María Soto", email="maria@example.com", role="Engineering"),
        ],
    )
    rfq.access_links = [
        AccessCategory(
            name="Workspaces",
            links=[
                AccessLink(label="SharePoint", url="https://example.sharepoint.com/rfq", owner_person_id=rfq.people[0].id),
                AccessLink(label="ERP supplier portal", url="https://erp.example/suppliers"),
            ],
        )
    ]
    rfq.milestones = [
        Milestone(title="Spec frozen", target_date=today - timedelta(days=5), status=MilestoneStatus.COMPLETE, owner_person_id=rfq.people[0].id),
        Milestone(title="RFQ sent", target_date=today + timedelta(days=10), status=MilestoneStatus.ACTIVE, owner_person_id=rfq.people[1].id),
        Milestone(title="Supplier shortlist", target_date=today + timedelta(days=30), status=MilestoneStatus.PLANNED, owner_person_id=rfq.people[1].id),
        Milestone(title="Award", target_date=today + timedelta(days=60), status=MilestoneStatus.BLOCKED, notes="Pending finance signoff."),
    ]
    rfq.tasks = [
        Task(title="Translate spec to RFQ template", column="Done", priority=Priority.MEDIUM, assignee_ids=[rfq.people[2].id], due_date=today - timedelta(days=8), milestone_id=rfq.milestones[0].id),
        Task(title="Compile supplier longlist", column="Done", priority=Priority.HIGH, assignee_ids=[rfq.people[1].id], due_date=today - timedelta(days=2), milestone_id=rfq.milestones[1].id),
        Task(title="Run risk scoring on suppliers", column="In Progress", priority=Priority.HIGH, assignee_ids=[rfq.people[1].id, rfq.people[0].id], due_date=today + timedelta(days=4), milestone_id=rfq.milestones[1].id),
        Task(title="Validate BOM against drawing rev D", column="In Progress", priority=Priority.CRITICAL, assignee_ids=[rfq.people[2].id], due_date=today + timedelta(days=2), milestone_id=rfq.milestones[1].id),
        Task(title="Negotiate NDA with new vendors", column="Blocked", priority=Priority.MEDIUM, assignee_ids=[rfq.people[0].id], due_date=today + timedelta(days=8), notes="Waiting on legal."),
        Task(title="Tooling cost benchmark", column="Backlog", priority=Priority.LOW, due_date=today + timedelta(days=25), milestone_id=rfq.milestones[2].id),
        Task(title="Award decision memo", column="Backlog", priority=Priority.MEDIUM, due_date=today + timedelta(days=55), milestone_id=rfq.milestones[3].id),
    ]
    storage.save_project(
        rfq,
        sections={
            "content": "## Scope\nReplace manual quoting on Line 12 with an automated RFQ pack.\n\n## Out of scope\nLine 11 retrofit.",
            "change_requests": "- 2026-04-12 — Drawing rev D adopted (replaces rev C).\n- 2026-04-20 — Added secondary tooling supplier as required option.",
            "roadblocks": "- Award milestone blocked until finance approves CapEx.\n- NDA delays on two suppliers.",
            "notes": "Weekly review every Tuesday 10:00.",
        },
        note="Seed demo data",
    )

    onboarding = Project(
        slug="customer-onboarding-v2",
        name="Customer Onboarding v2",
        description="Redesign the first-week experience for SMB customers.",
        health=HealthStatus.ON_TRACK,
        status=ProjectStatus.ACTIVE,
        start_date=today - timedelta(days=5),
        end_date=today + timedelta(days=45),
        people=[
            Person(name="Carla Méndez", email="carla@example.com", role="PM"),
            Person(name="Diego Ortiz", email="diego@example.com", role="Design"),
        ],
    )
    onboarding.milestones = [
        Milestone(title="Research synthesis", target_date=today + timedelta(days=7), status=MilestoneStatus.ACTIVE, owner_person_id=onboarding.people[0].id),
        Milestone(title="Prototype review", target_date=today + timedelta(days=21), status=MilestoneStatus.PLANNED, owner_person_id=onboarding.people[1].id),
        Milestone(title="Beta launch", target_date=today + timedelta(days=42), status=MilestoneStatus.PLANNED),
    ]
    onboarding.tasks = [
        Task(title="Interview 8 SMB customers", column="In Progress", priority=Priority.HIGH, assignee_ids=[onboarding.people[0].id], due_date=today + timedelta(days=5)),
        Task(title="Map current journey", column="In Progress", priority=Priority.MEDIUM, assignee_ids=[onboarding.people[1].id], due_date=today + timedelta(days=6)),
        Task(title="Draft v2 wireframes", column="Backlog", priority=Priority.HIGH, assignee_ids=[onboarding.people[1].id], due_date=today + timedelta(days=15), milestone_id=onboarding.milestones[1].id),
        Task(title="Beta cohort selection", column="Backlog", priority=Priority.MEDIUM, due_date=today + timedelta(days=35), milestone_id=onboarding.milestones[2].id),
    ]
    storage.save_project(
        onboarding,
        sections={
            "content": "## Goal\nCut activation time by 40%.",
            "change_requests": "",
            "roadblocks": "",
            "notes": "Coordinate with Support team.",
        },
        note="Seed demo data",
    )

    finance_close = Project(
        slug="finance-close-q2",
        name="Finance close Q2",
        description="Quarterly close with new ERP module live.",
        health=HealthStatus.BLOCKED,
        status=ProjectStatus.ACTIVE,
        start_date=today + timedelta(days=10),
        end_date=today + timedelta(days=40),
    )
    finance_close.milestones = [
        Milestone(title="Cutoff", target_date=today + timedelta(days=12), status=MilestoneStatus.PLANNED),
        Milestone(title="Reconciliations", target_date=today + timedelta(days=25), status=MilestoneStatus.PLANNED),
        Milestone(title="Board pack", target_date=today + timedelta(days=39), status=MilestoneStatus.PLANNED),
    ]
    storage.save_project(
        finance_close,
        sections={"content": "Quarterly close.", "change_requests": "", "roadblocks": "ERP module sign-off pending IT.", "notes": ""},
        note="Seed demo data",
    )

    quote_template = DocumentTemplate(
        slug="supplier-quote-pack",
        name="Supplier Quote Pack",
        description="Word document sent to each candidate supplier.",
        fields=[
            DocumentTemplateField(key="part_number", label="Part Number", aliases=["PN", "Item Number"], value="ABC-12345"),
            DocumentTemplateField(key="revision", label="Revision", aliases=["Rev"], value="D"),
            DocumentTemplateField(key="supplier_name", label="Supplier Name", aliases=["Vendor"], value=""),
            DocumentTemplateField(key="quoted_price", label="Quoted Price", field_type=DocumentFieldType.EXCEL_CELL, aliases=["Cost", "Unit Price"], value="Quote.xlsx!B12"),
            DocumentTemplateField(key="bom_table", label="BOM Table", field_type=DocumentFieldType.EXCEL_TABLE, aliases=["Bill of Materials"], required=False, value=""),
        ],
    )
    storage.save_document_template(quote_template)

    award_template = DocumentTemplate(
        slug="award-letter",
        name="Award Letter",
        description="Final award notification.",
        fields=[
            DocumentTemplateField(key="part_number", label="Material Number", aliases=["Part No"], value=""),
            DocumentTemplateField(key="supplier_name", label="Awarded Supplier", aliases=["Vendor"], value=""),
            DocumentTemplateField(key="award_date", label="Award Date", value=""),
        ],
    )
    storage.save_document_template(award_template)

    print("Seeded:", [p.slug for p in [rfq, onboarding, finance_close]])
    print("Doc templates:", [quote_template.slug, award_template.slug])


if __name__ == "__main__":
    main()
