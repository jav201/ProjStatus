# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Setup (Linux/macOS shown — README has the equivalent PowerShell):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,exports]"
python -m playwright install chromium   # only needed for PNG export
```

Common tasks:

- Run the dev server: `python -m uvicorn app.main:app --reload` (serves on `http://127.0.0.1:8000`)
- Run all tests: `python -m pytest` (`pyproject.toml` already sets `-q` and `testpaths = ["tests"]`)
- Run a single test: `python -m pytest tests/test_storage.py::test_create_project_writes_expected_files`
- Seed demo projects + document templates into the repo: `python seed_demo.py`
- Windows one-shot launcher (creates venv, installs, opens browser): `start_projstatus.bat`

There is no linter or formatter configured. PowerShell users should always invoke tools as `python -m <tool>` (see README for why).

## Architecture

ProjStatus is a single-process FastAPI app that renders server-side Jinja2 with htmx + SortableJS + Mermaid (all from CDN — see `app/templates/base.html`). There is no database: every project lives as a folder of files under `projects/<slug>/` and is the canonical source of truth.

### App factory and data root

`app.main.create_app(root_dir)` builds the FastAPI app. The **code root** (templates/static) is always under `app/`, but the **data root** (`projects/`, `exports/`, `project_templates/`, `document_templates/`) defaults to the repo root and is overridable. Tests rely on this — they call `create_app(tmp_path)` to get a fully isolated app per test (see `tests/test_routes.py`). When adding tests that touch storage, follow the same pattern; do not hard-code paths to the real `projects/` directory.

The module-level `app = create_app()` near the bottom of `app/main.py` is what `uvicorn app.main:app` loads.

### Storage service is the only writer

All disk I/O for projects flows through `app/services/storage.py::StorageService`. Routes in `app/main.py` should never write to the project filesystem directly — they always go through `storage.save_project(...)`, which in one atomic-ish step:

1. Writes the four section markdowns (`content.md`, `change_requests.md`, `roadblocks.md`, `notes.md`).
2. Writes `timeline.mmd` (regenerated from the model unless `preserve_timeline=True`).
3. Writes `project.json` with refreshed `sync_state` hashes.
4. Builds an `Addendum` (snapshot + unified diffs vs. the prior snapshot via `app/services/history.py`) and writes it to `history/<timestamp>.json` and `history/<timestamp>.md`.

Bypassing this loses history, breaks the external-edit detector, and risks file corruption — see the next two points.

### Two cross-platform file-write rules

- **Always use `_write_text(path, content)`** (in `storage.py`) instead of `Path.write_text`. The default `write_text` translates `\n` → `\r\n` on Windows; combined with read-time translation, that doubled CR-bearing newlines on each round-trip and slowly corrupted section files. `_write_text` forces `newline="\n"` and `utf-8`.
- `_heal_section_text` collapses runs of ≥4 newlines to 2 on read. Don't remove it: it repairs files damaged by the pre-fix bug. Two consecutive newlines is the most a Markdown source ever needs.

### Mermaid timeline two-way sync

`app/services/mermaid.py` is the round-trip between `project.json` (tasks/milestones) and `timeline.mmd`:

- `render_timeline(project)` always produces the canonical app-owned Mermaid (sections per board column, per-task ID lines, milestone lines).
- `import_timeline(project, text)` parses the canonical pattern back into the model; **only `title`, `dates`, and Mermaid status keywords (`active`, `done`, `crit`) round-trip**. Anything else marks `supported=False`.
- `load_project` calls `import_timeline` so external edits to `timeline.mmd` are detected and merged. If parsing finds anything unsupported, `sync_state.timeline_is_app_owned` flips to `False`.
- When `timeline_is_app_owned` is `False`, every `save_project` call in `main.py` passes `preserve_timeline=not loaded.project.sync_state.timeline_is_app_owned` so the user's hand-edited Mermaid is not overwritten by the regenerated version. **Preserve this pattern in any new mutation route** — search for the existing call sites if unsure.

The Mermaid ↔ domain status map is fixed: `active↔active`, `done↔complete`, `crit↔blocked`, missing token ↔ `planned`.

### Sync state and external-edit detection

`Project.sync_state` carries hashes for `project.json`, each section, and `timeline.mmd`. On `load_project`, current file hashes are compared to the saved hashes to detect edits made outside the app (Git pull, manual edit). Mismatches surface as a `sync_notice` banner and are listed in `external_changes`. `save_project` resets all hashes to the just-written content. If you change what files a project is composed of, update the hash bookkeeping in both `load_project` and `save_project`.

### Domain model (`app/models.py`)

Pydantic v2, `StrEnum` everywhere. A few load-bearing details:

- IDs: `make_id(prefix)` → `f"{prefix}_{uuid4().hex[:8]}"`. The Mermaid parser keys off these prefixes (`task_…`, `milestone_…`).
- `Task.column` is the kanban column; the `blocked` boolean was migrated away — `migrate_legacy_blocked` rewrites old `{"blocked": true}` JSON into `column: "Blocked"` on load. Don't reintroduce a separate `blocked` field.
- `Task.subtasks: list[Subtask]` lives only in `project.json` — `mermaid.py` never sees it. `task_completion(task)` returns 1.0 when `column == "Done"`; otherwise it's `done/total` over subtasks (0.0 with no subtasks). `progress_pct(project)` averages `task_completion` across all tasks. So adding subtasks to a non-Done task lifts the project KPI; moving a task to Done still scores 1.0 regardless of unchecked subtasks.
- `DictionaryEntry.key` and `DocumentTemplateField.key` must match `[A-Za-z_][\w]*` (validated by `_is_valid_dictionary_key` in `main.py` and the Jinja tag inspector).
- The default board columns come from `AppConfig.default_board_columns` (`Backlog / In Progress / Blocked / Done`). Mermaid status emission in `render_timeline` is hard-coded to those names; renaming columns will break Gantt status colors until you update `mermaid.py`.

### Word document templates

`app/services/storage.py::inspect_docx_tags` and `build_render_context` drive Word doc rendering with `docxtpl`. Tags scan `.docx` XML after stripping tags, because Word can split a single `{{ tag }}` across multiple `<w:t>` runs. The render context layers, in order: project metadata defaults (`project_name`, `today`, etc.) → template field values → project `dictionary` entries (per-project overrides). See `USER_GUIDE.md` for the user-facing tag syntax.

### History and restore

`history/<timestamp>.json` is a full `Addendum` (the entire `ProjectSnapshot` plus unified diffs vs. the previous snapshot). `restore_history` simply re-saves the snapshot through `save_project`, which means a restore *itself* creates a new addendum — there is no destructive rollback.

### Routes layout

All ~70 routes live in `app/main.py` inside `create_app`. Pages are server-rendered HTML; mutation endpoints are `POST` form submits that 303-redirect back to a GET (htmx is used selectively for partial swaps and drag-and-drop). Templates are split between full-page templates in `app/templates/` and project-tab partials in `app/templates/partials/`. The `render_template` helper merges every page with the sidebar/breadcrumb context built by `build_sidebar_context` — use it instead of `templates.TemplateResponse` directly so the shell stays consistent.

### Plan-tab Add menu (extensible)

The "+" dropdown next to the Board/Gantt segmented toggle (`app/templates/project.html`) opens one of the side panels in `app/templates/partials/_plan_add_panels.html` (Add Task, Add Milestone). The wiring uses a generic attribute convention discovered in `initializeTaskSidePanel` (`app/static/app.js`):

- Trigger: `<button data-add-open="X">` (X = `task` | `milestone` | …)
- Panel: `<aside data-add-panel="X">`
- Close button inside the panel: `<button data-add-close>`

To add a third object type, append a `<button data-add-open="risk">` to the menu, append a `<aside data-add-panel="risk">` to the partial, and write the route. No JS changes needed.

The Add Milestone form posts a hidden `return_to=plan` so `milestone_create/update/delete` redirect to the Board instead of the default Summary; existing call sites without that field keep the unchanged Summary redirect (see `milestone_return_url` in `app/main.py`).

### Storage layout on disk

```
projects/<slug>/
  project.json              # Pydantic-serialized Project, with sync_state hashes
  content.md change_requests.md roadblocks.md notes.md
  timeline.mmd              # canonical app-owned, unless user introduces unsupported lines
  history/<timestamp>.json  # full Addendum (snapshot + diffs)
  history/<timestamp>.md    # human-readable rendering of the same
project_templates/<slug>.json
document_templates/<slug>.json
document_templates/<slug>/template.docx   # optional uploaded Word file
exports/<timestamp>/        # batch-export output
```

`projects/*/` is gitignored except for `.gitkeep`; demo seed data is generated, not committed.
