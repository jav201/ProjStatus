# ProjStatus User Guide

ProjStatus is a local-first project management application. It stores projects, templates, document field maps, history, and exports as files inside this repository, so the workspace can be reviewed with Git and edited outside the app when needed.

## Start the Application

From the repository root:

```powershell
python -m uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

On Windows, you can also run:

```powershell
.\start_projstatus.bat
```

## Main Navigation

- `Dashboard`: Portfolio view of all projects.
- `New Project`: Create a blank project or create one from a project template.
- `Templates`: Manage project templates and document templates.
- `Exports`: Export selected projects to supported output formats.

## Create a Project

1. Open `New Project`.
2. Enter a project name, description, start date, and end date.
3. Select `Blank project` or choose a saved project template.
4. Click `Create project`.

Example:

```text
Project name: RFQ Line 12 Automation
Description: Track engineering, sourcing, and supplier quote readiness.
Start date: 2026-05-01
End date: 2026-07-15
Project template: Launch Template
```

The app creates a folder under:

```text
projects/rfq-line-12-automation/
```

That folder contains the project JSON, Markdown sections, Mermaid timeline, and history snapshots.

## Use Dashboard Views

The dashboard has a `View` selector:

- `Cards`: Best for quick project review.
- `Gantt`: Shows all dated projects on one portfolio timeline.
- `Table`: Best for comparing project status, owners, dates, roadblocks, and next milestones.

For the Gantt view to show a project, the project needs at least a start date or end date. Milestones with target dates appear as markers inside the project bar.

## Manage a Project

Open a project from the dashboard. The project workspace includes:

- `Overview`: Project metadata, milestones, project actions, and template creation.
- `View Mode`: Read-only summary views for presentations and reviews.
- `Board`: Kanban-style task tracking.
- `Timeline`: Mermaid timeline editor.
- `People & Access`: Stakeholders and project links.
- `Sections`: Markdown content, change requests, roadblocks, and notes.
- `History`: Saved addendums and restore points.

## Save a Project as a Template

1. Open a project.
2. Go to `Overview`.
3. In `Project actions`, find `Save as template`.
4. Enter a template name and notes.
5. Click `Create template`.

Example:

```text
Template name: Supplier RFQ Project Template
Template notes: Use for supplier quote projects with milestones, board columns, and standard sections.
```

The template is stored as:

```text
project_templates/supplier-rfq-project-template.json
```

When creating a new project, select this template from the `Project template` dropdown. The new project copies starter milestones, tasks, people, access links, sections, and timeline structure.

## Document Templates

Document templates define the information required to complete a document package. They are useful when several documents need the same project or product data, but each document may use different names for the same field.

Open `Templates`, then use `Create document template`.

Each field line uses this format:

```text
key|label|type|aliases|required_or_optional|value
```

Where:

- `key`: Canonical internal name used to homologate equivalent fields.
- `label`: Display name shown to users.
- `type`: One of `string`, `excel_table`, or `excel_cell`.
- `aliases`: Alternate names used by other documents, separated by commas.
- `required_or_optional`: Use `required` or `optional`.
- `value`: Current value. Leave blank when missing.

## Document Tag Examples

### Simple String Field

Use this for normal text values such as part numbers, customer names, revision levels, owners, or supplier names.

```text
part_number|Part Number|string|PN,Item Number,Material Number|required|
```

This means:

- Canonical key: `part_number`
- Display label: `Part Number`
- Type: text string
- Equivalent labels: `PN`, `Item Number`, `Material Number`
- Required: yes
- Current value: missing

If the value is known:

```text
part_number|Part Number|string|PN,Item Number,Material Number|required|ABC-12345
```

### Excel Cell Field

Use this when a specific Excel cell should provide the value.

```text
quoted_price|Quoted Price|excel_cell|Unit Price,Cost,Quote|required|Quote.xlsx!B12
```

This records that the required value is expected from cell `B12` in `Quote.xlsx`.

Another example:

```text
annual_volume|Annual Volume|excel_cell|EAU,Estimated Annual Usage|required|Demand.xlsx!C8
```

### Excel Table Field

Use this when the needed information is a table, not a single cell.

```text
bom_table|Bill of Materials|excel_table|BOM,Part List,Material List|required|BOM.xlsx!A1:H40
```

This records that the document needs a BOM table from the range `A1:H40`.

Another example:

```text
tooling_cost_table|Tooling Cost Table|excel_table|Tooling,CapEx,Investment|required|
```

This field is required but missing because the value is blank.

## Homologating Fields Across Documents

Use the same `key` when different documents refer to the same information with different labels.

Example document template A:

```text
part_number|Part Number|string|PN,Item Number|required|ABC-12345
```

Example document template B:

```text
part_number|Material Number|string|Part No,Component ID|required|
```

Both fields use the same canonical key:

```text
part_number
```

The `Templates` page groups these under `Field homologation`, showing:

- the canonical key
- all labels used across documents
- all aliases
- how many documents use the field
- how many required values are missing

This lets you treat `Part Number`, `Material Number`, `PN`, and `Component ID` as the same required business field.

## Completion Percentage

Each document template calculates completion based on required fields only.

Example:

```text
part_number|Part Number|string|PN|required|ABC-12345
supplier_name|Supplier Name|string|Vendor|required|
quoted_price|Quoted Price|excel_cell|Cost|required|Quote.xlsx!B12
bom_table|BOM Table|excel_table|Bill of Materials|optional|
```

Required fields:

- `part_number`: filled
- `supplier_name`: missing
- `quoted_price`: filled

Completion:

```text
2 filled required fields / 3 required fields = 67%
```

The optional `bom_table` does not reduce the completion percentage.

## Recommended Document Template Patterns

Use stable canonical keys:

```text
part_number
revision
supplier_name
quoted_price
annual_volume
bom_table
tooling_cost_table
```

Avoid creating different keys for the same concept:

```text
part_number
pn
item_number
material_number
```

Instead, use one canonical key and put the alternate names in `aliases`:

```text
part_number|Part Number|string|PN,Item Number,Material Number|required|
```

## Current Document Template Scope

The current implementation stores document template definitions, required tags, aliases, values, missing-field status, completion percentage, and homologation groups.

It does not yet automatically parse uploaded Word, PDF, or Excel files. For now, enter the value or source reference manually, such as:

```text
Quote.xlsx!B12
BOM.xlsx!A1:H40
ABC-12345
Supplier One
```

The next natural enhancement is to add document file uploads and automatic extraction from Excel cells and tables.

## Exports

Open `Exports`, select one or more projects, choose formats, and run the export. HTML and PPTX exports work from the base app. PNG export requires Playwright and Chromium.

Install export dependencies with:

```powershell
python -m pip install -e ".[exports]"
python -m playwright install chromium
```

## Storage Reference

Project data:

```text
projects/<project-slug>/
```

Project templates:

```text
project_templates/<template-slug>.json
```

Document templates:

```text
document_templates/<template-slug>.json
```

Exports:

```text
exports/
```
