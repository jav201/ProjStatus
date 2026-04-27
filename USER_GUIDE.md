# ProjStatus User Guide

ProjStatus is a local-first project management application. Project data, project templates, document templates, history, and exports all live as files inside the repository, so the workspace can be reviewed with Git and edited outside the app.

## Start the application

From the repository root:

```powershell
python -m uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000`. On Windows you can also run `.\start_projstatus.bat`.

## Top navigation

- **Dashboard** — portfolio of every project, with three views: Cards, Gantt, Table.
- **New Project** — create a blank project or one based on a project template.
- **Templates** — manage project templates and Word document templates.
- **Exports** — export selected projects to HTML, PNG, or PPTX.

## Dashboard

The dashboard is a single page with a search box, health filter, sort selector, and a segmented `Cards | Gantt | Table` toggle. It updates as you change a control — no Apply button.

- **Cards** view: each project shows a Health badge, dates, owners, next milestone, blocked-tasks count, and last update (relative time). One primary `Open` button plus a `⋯` menu for Present, Board, Export, Duplicate, Archive.
- **Gantt** view: a portfolio Gantt with month tick marks across the top, today line, and per-project bars colored by health. A legend explains the colors.
- **Table** view: one row per project with health, dates, owners, roadblocks, next milestone, and "updated".

## Project workspace

Each project page has four main tabs plus History on the right:

- **Summary** — KPI cards (people / milestones / tasks / blocked), upcoming milestones, roadblocks, people directory, an "Edit project details" panel, Duplicate / Save-as-template forms, and a footer **Danger zone** that holds the permanent-delete control.
- **Plan** — sub-toggle for `Board | Gantt`. The Board is a Kanban with drag-and-drop and a side panel for editing a task (title, dates, milestone, assignees). The Gantt is the editable Mermaid timeline.
- **People** — stakeholders and access links.
- **Notes** — sub-toggle across the four Markdown sections: Content, Change requests, Roadblocks, Notes.
- **History** — addendums, with diffs and a one-click Restore.

A **Present** button in the project header switches to a chrome-free executive snapshot for screen sharing.

## Word document templates — how to write tags

Each document template links a `.docx` file you upload to a list of named **fields**. Inside the Word document you use Jinja-style tags. They are substituted with the field values plus a few project-derived defaults whenever you click **Download filled** for a project.

### Single value

In Word, type:

```
{{ part_number }}
```

In ProjStatus, define a field with key `part_number`. The downloaded document contains the field's current value. Tag keys are case-sensitive and must use only `[a-zA-Z_]\w*`.

### Always-available project fields

The following keys are populated automatically — you don't need to add them as fields:

```
{{ project_name }}
{{ project_description }}
{{ project_status }}
{{ project_health }}
{{ project_start_date }}
{{ project_end_date }}
{{ today }}
```

### Loops over project data

`milestones` and `people` are exposed as lists. Use Jinja `{% for %}`:

```
{% for m in milestones %}- {{ m.title }} ({{ m.status }} – {{ m.target_date }})
{% endfor %}

{% for p in people %}{{ p.name }} – {{ p.role }} – {{ p.email }}
{% endfor %}
```

### Quote-pack example

A `Supplier Quote Pack` document might contain:

```
Subject: Quote request for {{ part_number }} ({{ project_name }})

Dear {{ supplier_name }},

Please provide a quote for the following:
  – Part number: {{ part_number }}
  – Revision: {{ revision }}
  – Annual volume: {{ annual_volume }}

Please respond by {{ project_end_date }}.

Regards,
The {{ project_name }} team — {{ today }}
```

### How the upload works

1. Open **Templates**.
2. Pick a document template (or create one with at least one field).
3. Click **Upload .docx** under the template card and select your Word file.
4. The page redraws with a "Tags found in this document" table showing every `{{ tag }}` you used and whether it's mapped to a field, filled, missing, or unmapped.
5. Pick a project from the **Download filled** dropdown and click the button — the rendered `.docx` downloads.

### Field metadata you can also store

Each field row carries a key, a friendly label, a type (`string`, `excel_cell`, `excel_table`), a list of aliases (alternate names other documents use for the same value), a required/optional flag, and a current value. Aliases are used by the **Field homologation** panel to flag when two documents call the same data by different names.

The current implementation substitutes the `value` text directly into the document. Excel cell/range references such as `Quote.xlsx!B12` are stored as plain strings — automatic Excel extraction is on the roadmap.

## Project templates

Open a project, scroll down to **Save as project template** in the Summary tab, name it, and click Create template. To create a project from one, open **New Project** and choose your template.

## Storage layout

```
projects/<slug>/
  project.json
  content.md
  change_requests.md
  roadblocks.md
  notes.md
  timeline.mmd
  history/<timestamp>.json
  history/<timestamp>.md

project_templates/<slug>.json
document_templates/<slug>.json
document_templates/<slug>/template.docx   (optional uploaded Word file)

exports/
```

`timeline.mmd` is editable, but the round-trip back into `project.json` only carries title, dates, and Mermaid status keywords (`active`, `done`, `crit`). Any unrecognized line surfaces as a yellow banner on the Plan → Gantt page.

## Exports

Open **Exports**, pick projects + formats, and run. HTML and PPTX work out of the box. PNG requires Playwright with Chromium:

```powershell
python -m pip install -e ".[exports]"
python -m playwright install chromium
```

To enable Word filling:

```powershell
python -m pip install -e ".[docx]"
```
