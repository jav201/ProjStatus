# Increment 007 — US-005 Settings page (Phase 3 closes)

**Batch:** `2026-05-04-batch-01` · **Phase:** 3 · **Increment:** 7 / 7 · **Date:** 2026-05-05

## 1 · What changed

Three LLRs implemented — the final user-story increment of phase 3.

- **LLR-010.1** — New `GET /settings` route in `app/main.py`. Renders `app.state.config.root_dir` (the data root), `app.state.user`, and a peer-rows list with `(label, path, writable, reachable)` per peer. Reachability uses `Path.resolve(strict=False).is_dir()` (per the iter-3 doc update).
- **LLR-010.2** — New template `app/templates/settings.html`. Extends `base.html`. Contains no `<form>`, `<input>`, `<button type=submit>`, or `method=post` markup. Header comment documents the non-mutating invariant without using literal markup tokens (so static-source inspection stays clean).
- **LLR-011.1** — `/settings` is registered ONLY as a GET handler. The absence of POST/PUT/PATCH/DELETE handlers is the enforcement; FastAPI returns the framework default `405 Method Not Allowed` for unregistered methods on a registered path.

Plus one sidebar wiring change so the Settings page is reachable from any page (per LLR-010.1's "reachable from the sidebar" acceptance):
- `build_sidebar_context` in `app/main.py` now resolves `active_nav = "settings"` for paths starting with `/settings`.
- `app/templates/base.html` adds a `<a class="sidebar-link" href="…/settings">⚙ Settings</a>` link after Exports.

**TCs added (10):**

- **TC-010** (HLR-010 behavioural) — `GET /settings` returns 200; body contains `data_root` path, peer label, and user.
- **TC-031** (LLR-010.1) — Writable peer renders `RW`; missing-path peer renders `unreachable`. Separate test for read-only peer rendering `RO` (decoupled assertions).
- **TC-032** (LLR-010.2 inspection) — Source-level grep against `app/templates/settings.html`: zero matches for `<form`, `<input`, `<button[^>]*type=.submit`, `method=.post`. First non-comment line equals `{% extends "base.html" %}`.
- **TC-011 / TC-033 (×4)** — Parametrized over `POST`, `PUT`, `PATCH`, `DELETE` against `/settings`; each returns 405.
- **TC-033 (route-table)** — Inspects `app.routes` directly; only `{GET, HEAD}` methods are allowed on `/settings`.
- **Sidebar integration** — Home page renders a link with `href="/settings"`.

## 2 · Files modified (4 / 5 cap)

| Path | Change |
|------|--------|
| [app/main.py](app/main.py) | New `GET /settings` route handler (38 lines incl. docstring + reachability loop). New `elif path.startswith("/settings"):` branch in `build_sidebar_context`. |
| [app/templates/settings.html](app/templates/settings.html) | NEW: 50 lines. 3 cards (Data root / User / Peer roots) with no mutating markup. |
| [app/templates/base.html](app/templates/base.html) | Sidebar nav: 3-line addition for the Settings link with active-state binding. |
| [tests/test_settings_page.py](tests/test_settings_page.py) | NEW: 10 tests covering TC-010, TC-031 (×2), TC-032, TC-011 / TC-033 (×4 parametrized + 1 route-table inspection), plus sidebar-link presence. |

4 files total — under the 5-file cap.

## 3 · How to test

```
.venv/Scripts/python -m pytest tests/test_settings_page.py -v
.venv/Scripts/python -m pytest                                          # full suite
```

## 4 · Test results

**Targeted (`tests/test_settings_page.py`):** 10 passed.

**Full suite (regression check):**

```
138 passed, 1 warning in 10.14s
```

Pre-Increment-7 baseline was 128 tests. +10 → **138**. No new warnings; the single existing warning (Pydantic enum serializer in `tests/test_subtasks.py`) is unaffected.

## 5 · Risks

1. **Reachability uses `Path.resolve` + `is_dir()`** — does NOT detect a path that exists but is permission-denied at runtime (R-006). Documented as a known limitation. The route handler swallows `OSError` in the `try` block to keep the page from crashing on edge-case paths.
2. **No CSS for the new `.settings-peer-list` / `.settings-peer-row` / `.settings-value` classes.** Browsers render with default `<ul>`/`<li>` styling. Polish follow-up (no LLR mandates visual treatment).
3. **`/settings` exposes `data_root`, peer paths, and the username** — per §2.4 loopback-only threat model, this is acceptable. Operators binding to non-loopback interfaces are responsible per the constraint (M-S-003 acknowledgement).
4. **Source-level inspection (TC-032) caught my own Jinja comment** that listed forbidden token literals. Comment rewritten to describe the invariant without using the literals. Worth flagging for any future template author: don't put literal `<form>`-style strings in Jinja comments inside `settings.html`.
5. **No CRs touched or closed by this increment.** US-005 is now complete; CR-009 (`.gitignore` recommendation in USER_GUIDE.md) is a phase-6 doc-only follow-up, not relevant to the Settings page itself.

## 6 · CR backlog status

Unchanged — 5/10 closed, 5 remaining (0 HIGH, 1 MEDIUM CR-006, 4 LOW CR-007/-008/-009/-010).

## 7 · Phase 3 — final state

| Metric | Value |
|---|---|
| LLRs implemented | **24 / 24** ✅ |
| HLRs covered | **14 / 14** ✅ (HLR-001..HLR-014, with US-001 covered indirectly via existing PR #18 work) |
| TCs in suite | 138 (38 batch TCs + 100 pre-existing) |
| CRs closed | 5 / 10 (CR-001 HIGH, CR-002 HIGH, CR-003, CR-004, CR-005) |
| CRs still open | 5 — 1 MEDIUM (CR-006), 4 LOW (CR-007, CR-008, CR-009, CR-010) |
| Increments completed | 7 (1, 2, 3, 4, 5, 6a, 6b, 7) |
| Files touched across phase 3 | 13 (8 source, 5 test) |
| Net diff vs. main | ~+1100 lines source/template/test (net new feature surface for US-002, US-003, US-004, US-005) |

## 8 · Pending items

- **Open CRs** — CR-006 (venv-path demotion), CR-007 (`actor=unknown` carve-out doc), CR-008 (TC-035 compound semantics — already mitigated by separate test functions), CR-009 (`.gitignore` callout), CR-010 (12 deferred minors bundled).
- **CSS polish** — `.week-chip`, `.inbox-claimed`, `.settings-peer-row` classes are rendered but unstyled. Phase-6 candidate.

## 9 · Suggested next task — Phase 4 — Validation

Phase 3 is now complete. Phase 4 executes the validation strategy defined in §5.2 of `01-requirements.md`:

- Run all 38 TCs (already passing in the suite — they ARE the validation evidence).
- For each TC, record `pass | fail | pending` in `04-validation.md`.
- Capture pytest output + any `inspection`-method evidence (e.g., grep results on `settings.html`).
- Verify the LLR-014.1 manual UAT step (the `%V` token actually renders as `Wnn` in the Mermaid CDN pinned by `base.html`) — the only piece that pytest cannot prove.
- Phase-4 gate: blocker fails force iterate to phase 3; otherwise the user decides.

The qa-reviewer agent runs phase 4. Recommended invocation: `/dev-flow-en` to advance.

---

**Stop.** Increment 7 is complete. Phase 3 closes.
