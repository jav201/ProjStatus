# Increment 001 — ISO 8601 week-label helper + Jinja global

**Batch:** `2026-05-04-batch-01` · **Phase:** 3 · **Increment:** 1 / N · **Date:** 2026-05-04

## 1 · What changed

Two LLRs implemented:

- **LLR-006.1** — added `iso_week_label(d: date | None) -> str` to `app/utils.py`. Returns `f"W{d.isocalendar().week:02d}"` for a non-null `date`, empty string for `None`. Pure stdlib, no new dependencies.
- **LLR-007.2** — registered `iso_week_label` as a Jinja global in `app/main.py::create_app` so templates can call `{{ iso_week_label(task.start_date) }}` directly without per-route context injection.

Three test cases added (all green):

- **TC-006** — HLR-006 behavioural acceptance: `iso_week_label(date(2026, 4, 27)) == "W18"`.
- **TC-025** — LLR-006.1 boundary fixtures (parametrized over the 6 §5.4.A cases) plus the `None` case.
- **TC-027** — LLR-007.2 Jinja-global registration: `app.state.templates.env.globals["iso_week_label"] is iso_week_label`, plus a tiny inline `env.from_string("{{ iso_week_label(d) }}").render(d=date(2026,4,27)) == "W18"` functional check.

## 2 · Files modified

| Path | Change |
|------|--------|
| [app/utils.py](app/utils.py) | +5 lines: new `iso_week_label` function appended after `format_date` (line 42–45). |
| [app/main.py](app/main.py) | +2 lines: extended the `from app.utils import …` line to add `iso_week_label`; registered the Jinja global next to `format_date` / `format_when` at line 72. |
| [tests/test_iso_week_label.py](tests/test_iso_week_label.py) | NEW: 41 lines. 4 test functions (one parametrized → 6 boundary cases). |

3 files total — well under the 5-file cap.

## 3 · How to test

```
.venv/Scripts/python -m pytest tests/test_iso_week_label.py -v   # targeted
.venv/Scripts/python -m pytest                                   # full suite (regression)
```

Per CLAUDE.md and `pyproject.toml`, `-q` and `testpaths = ["tests"]` are already in effect; plain `python -m pytest` works. From a fresh worktree, dev extras must be installed first: `python -m pip install -e ".[dev,exports]"` (this increment's session installed `pytest 8.4.2`, `httpx`, `pluggy`, `iniconfig`, `pygments`, `packaging`, `certifi` — all of which are pulled by the `dev` extra in `pyproject.toml`).

## 4 · Test results

**Targeted (`tests/test_iso_week_label.py`):**

```
============================= test session starts =============================
platform win32 -- Python 3.12.7, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\jjgh8\OneDrive\Documents\Github\ProjStatus\.claude\worktrees\zen-leavitt-f6dd3b
configfile: pyproject.toml
plugins: anyio-4.13.0
collected 9 items

tests\test_iso_week_label.py .........                                   [100%]

============================== 9 passed in 0.77s ==============================
```

(9 = 1 TC-006 + 6 parametrized TC-025 + 1 None case + 1 TC-027.)

**Full suite (regression check):**

```
70 passed, 1 warning in 6.57s
```

Pre-increment baseline was 61 tests; this increment added 9 → 70 passing. The single warning is the pre-existing `tests/test_subtasks.py::test_task_update_route_persists_subtasks` Pydantic serializer warning that has nothing to do with this increment.

## 5 · Risks

1. **Python 3.12 `date.isocalendar()` API.** Returns an `IsoCalendarDate` namedtuple with `.week` attribute access. The repo pins `requires-python = ">=3.12"` (verified by `pyproject.toml`); the venv runs 3.12.7. No risk.
2. **Additive Jinja global.** The global registration is purely additive — existing templates that didn't reference `iso_week_label` are unaffected. The full-suite regression confirms no template break. No risk.
3. **Type-hint widening.** LLR-006.1's statement signature is `iso_week_label(d: date) -> str`, but the implementation accepts `date | None` to satisfy the "returns the empty string for `None` and does not raise" acceptance bullet. This matches the existing pattern of `format_date(value: date | None) -> str`. No risk; the LLR statement's narrower signature is the contract for non-null callers and the broader implementation is strictly compatible.
4. **No CRs blocked by this increment.** Increment 1 does not touch any code paths covered by CR-001..CR-010, so the deferred backlog is unchanged.

## 6 · Pending items

The following remain explicitly **NOT covered** by this increment:

- HLR-007.1 — task-card chip rendering (`app/templates/partials/project_board.html`).
- HLR-008.1 — milestone-row chip rendering (`app/templates/partials/_milestones_list.html`).
- HLR-009.1 / LLR-009.2 — Mermaid `axisFormat` week token, round-trip stability.
- HLR-014 / LLR-014.1 — Mermaid token verification + fallback decision.
- All US-002 / US-003 / US-005 LLRs (writable peers, identity gating, Settings page).
- CR-002, CR-003, CR-004, CR-008 (deferred items that touch later increments).

## 7 · Suggested next task

**Increment 2 — Template-side chip rendering for tasks and milestones.**

- Scope: LLR-007.1 (task-card chip) + LLR-008.1 (milestone-row chip).
- Files (estimated 3): `app/templates/partials/project_board.html`, `app/templates/partials/_milestones_list.html`, `tests/test_week_chip_rendering.py` (NEW).
- TCs: TC-007 (HLR-007 behavioural — board HTML contains `W18`), TC-008 (HLR-008 behavioural — milestone HTML contains `W19`), TC-026 (LLR-007.1 — all 5 fixture cases including the no-chip negative path), TC-028 (LLR-008.1 — milestone chip + null target_date no-chip path).
- Dependencies: requires LLR-006.1 + LLR-007.2 (this increment) — satisfied.
- No CRs need to be addressed in this increment.

Estimated effort: ~25 minutes. Two template additions (a single `<span class="week-chip">…</span>` block each) plus one test file.

---

**Stop.** Increment 1 is complete. No Increment 2 work has begun. Awaiting user approval before proceeding.
