# Increment 002 — Week chip on task cards and milestone rows

**Batch:** `2026-05-04-batch-01` · **Phase:** 3 · **Increment:** 2 / N · **Date:** 2026-05-04

## 1 · What changed

Two LLRs implemented:

- **LLR-007.1** — task-card partial in `app/templates/partials/project_board.html` now renders `<span class="week-chip">Wnn</span>` whenever `task.start_date` is non-null, suffixed with `–Wmm` when `task.due_date` falls in a different ISO week from `task.start_date`. The template uses the `iso_week_label` Jinja global registered in Increment 1 (LLR-007.2). Note: the LLR's `end_date` maps to the model's `due_date` field — this is the natural mapping in the existing Task schema (`app/models.py:95`).
- **LLR-008.1** — milestone-row partial in `app/templates/partials/_milestones_list.html` now renders a separate `<span class="week-chip">Wnn</span>` chip immediately after the existing `chip-muted` date chip whenever `milestone.target_date` is set.

Six test cases added (all green):

- **TC-007** (HLR-007 behavioural) — board HTML for a task with `start=2026-04-27, due=2026-04-29` contains `W18` and `class="week-chip"`.
- **TC-008** (HLR-008 behavioural) — board HTML for a milestone with `target=2026-05-04` contains `W19` and `class="week-chip"`.
- **TC-026** (LLR-007.1) — parametrized over the four positive-case fixtures from §5.4.B (same-week, multi-week, no-end, end-before-start) plus a separate negative test for `start_date=None`. The negative case is verified by exercising the template's chip-block conditional directly via the Jinja env, because the full route → storage round-trip defaults `None` to today's date (pre-existing `render_timeline` behavior; out of scope for this increment, will be addressed by HLR-009 / LLR-009.1).
- **TC-028** (LLR-008.1) — milestone with no `target_date` renders no chip via the route (milestones don't get the date defaulting that tasks do, so the negative case works through the route path cleanly).

## 2 · Files modified

| Path | Change |
|------|--------|
| [app/templates/partials/project_board.html](app/templates/partials/project_board.html:23) | +1 line: new week-chip span inserted in the chip-row between the priority chip and the existing due-date chip-muted. |
| [app/templates/partials/_milestones_list.html](app/templates/partials/_milestones_list.html:21) | +1 chip: appended `<span class="week-chip">{{ iso_week_label(m.target_date) }}</span>` immediately after the existing `chip-muted` date chip (still inside the `{% if m.target_date %}` guard). |
| [tests/test_week_chip_rendering.py](tests/test_week_chip_rendering.py) | NEW: 121 lines. 6 test functions (one parametrized → 4 cases + 4 standalone). |

3 files total — well under the 5-file cap.

## 3 · How to test

```
.venv/Scripts/python -m pytest tests/test_week_chip_rendering.py -v
.venv/Scripts/python -m pytest                                          # full suite
```

## 4 · Test results

**Targeted (`tests/test_week_chip_rendering.py`):**

```
============================= test session starts =============================
platform win32 -- Python 3.12.7, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\jjgh8\OneDrive\Documents\Github\ProjStatus\.claude\worktrees\zen-leavitt-f6dd3b
configfile: pyproject.toml
plugins: anyio-4.13.0
collected 8 items

tests\test_week_chip_rendering.py ........                               [100%]

============================== 8 passed in 2.00s ==============================
```

(8 = 1 TC-007 + 1 TC-008 + 4 parametrized TC-026 + 1 TC-026 negative + 1 TC-028.)

**Full suite (regression check):**

```
78 passed, 1 warning in 8.12s
```

Pre-Increment-2 baseline was 70 tests (Increment 1 closed at 70). +8 → 78. No new warnings; the single existing warning is the pre-existing `tests/test_subtasks.py::test_task_update_route_persists_subtasks` Pydantic serializer message, unaffected by this increment.

## 5 · Risks

1. **`render_timeline` defaults `None` start_date to today.** Discovered while writing TC-026: a task created via `client.post(...)` with `start_date=""` ends up loaded back with `start_date=date.today()` due to `render_timeline → import_timeline` round-trip. The Jinja-direct negative test bypasses this. The pre-existing behavior is unchanged by this increment but will be touched by HLR-009 / LLR-009.1 (Mermaid axis token + round-trip) in a later increment. Documented here so the future increment knows to consider whether to preserve `None`-as-`None` instead of defaulting.
2. **`end_date` ↔ `due_date` naming.** The requirements doc (§4 LLR-007.1, §5.4.B fixtures) uses `end_date` as a generic label; the actual `Task` model field is `due_date`. The template uses `task.due_date` and the test fixtures pass values to the form's `due_date` input. No drift in implementation; flagged here for documentation continuity in case CR-010 wants to harmonize the wording in the doc.
3. **Chip ordering on the task card.** I inserted the week-chip BETWEEN the priority chip and the due-date chip-muted. If the team prefers different ordering (e.g., week-chip after due-date), it's a one-line move. LLR-007.1 says "adjacent to its date metadata" which the current ordering satisfies (week-chip is directly to the left of the date chip).
4. **No CSS for `.week-chip`.** The class is rendered but no styling exists yet in `app/static/styles.css` or `styles.redesign.css`. Browser will fall back to default span styling (inline, no padding, no color). Adding CSS is out of scope for these LLRs (no LLR mandates visual treatment), but worth noting — the user may want to add a small CSS rule for visual polish in a follow-up.
5. **No CRs touched or closed by this increment.** CR-002 / CR-003 / CR-004 (Mermaid round-trip + token) belong to the next Mermaid-axis increment.

## 6 · Pending items

The following remain explicitly **NOT covered** by this increment:

- HLR-009 / LLR-009.1 / LLR-009.2 — Mermaid `axisFormat` week token + round-trip stability.
- HLR-014 / LLR-014.1 — Mermaid token verification + fallback.
- All US-002 / US-003 / US-005 LLRs (writable peers, identity gating, Settings page).
- CR-002 (LLR-009.2 round-trip tautology), CR-003 (`%V` constant), CR-004 (LLR-009.2 list naming) — to be addressed in the next Mermaid increment.
- CSS styling of `.week-chip` (not required by any LLR, optional polish).

## 7 · Suggested next task

**Increment 3 — Mermaid Gantt week labels (HLR-009 / HLR-014 + their LLRs) and address related CRs.**

- Scope: LLR-009.1 (week token confined to `axisFormat`) + LLR-009.2 (round-trip stability) + LLR-014.1 (token verification + fallback).
- Address in the same pass: **CR-002** (deepcopy round-trip), **CR-003** (`ISO_WEEK_AXIS_TOKEN` module constant), **CR-004** (return-list naming).
- Files (estimated 3): `app/services/mermaid.py`, `tests/test_mermaid_labels.py` (extend existing), and possibly `app/services/mermaid.py` once for the constant. No new test file needed if the existing `test_mermaid_labels.py` is the right home for TC-009 / TC-014 / TC-029 / TC-030 / TC-038.
- TCs: TC-009 (HLR-009 axis token), TC-014 (HLR-014 + round-trip ok flag), TC-029 (LLR-009.1 W in axisFormat only), TC-030 (LLR-009.2 round-trip), TC-038 (LLR-014.1 fallback assertion).
- Dependencies: requires LLR-006.1 (Increment 1, done). No dep on Increment 2.
- Estimated effort: ~30 minutes — Mermaid render line change + round-trip test + CR-002/003/004 fixes.

---

**Stop.** Increment 2 is complete. No Increment 3 work has begun. Awaiting user approval before proceeding.
