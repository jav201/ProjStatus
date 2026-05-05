# Increment 003 — Mermaid Gantt week labels + close CR-002/-003/-004

**Batch:** `2026-05-04-batch-01` · **Phase:** 3 · **Increment:** 3 / N · **Date:** 2026-05-04

## 1 · What changed

Three LLRs implemented + three CRs closed.

**LLRs implemented:**
- **LLR-009.1** — week token confined to the `axisFormat` line of `render_timeline`. The literal `W` now appears only on that line (verified by TC-029). No per-task or per-milestone token conveys the week.
- **LLR-009.2** — round-trip stability. `import_timeline(p, render_timeline(p))` returns `ok=True` and `render_timeline(imported) == rendered_before` after a `deepcopy` (verified by TC-030).
- **LLR-014.1** — module-level constant `ISO_WEEK_AXIS_TOKEN: Final[str] = "%V"` added to `app/services/mermaid.py`. Both `render_timeline` and the tests import it. The fallback path is now a one-line constant change rather than a doc-only convention.

**CRs closed:**
- **CR-002 (HIGH — correctness)** — round-trip tautology fixed. LLR-009.2 + TC-030 now use `deepcopy(p)` so the equality check is non-vacuous.
- **CR-003 (MEDIUM — testability)** — machine-readable signal source. `ISO_WEEK_AXIS_TOKEN` constant exported; tests import it; conditional `%V`-absence assertion now executable from pytest without parsing the review packet.
- **CR-004 (MEDIUM — correctness/docs)** — returned-list naming. LLR-009.2 + TC-014/TC-030/TC-038 now use `_imported_msgs, _errors` matching the actual `import_timeline` return shape.

**TCs added (5):**
- **TC-009** (HLR-009 behavioural) — `axisFormat` line contains `ISO_WEEK_AXIS_TOKEN`.
- **TC-014** (HLR-014 behavioural) — literal `W` in axisFormat + round-trip `ok=True` + conditional `%V` absence.
- **TC-029** (LLR-009.1) — literal `W` appears ONLY on the `axisFormat` line, never on per-task/milestone lines.
- **TC-030** (LLR-009.2) — deepcopy round-trip is byte-identical and `ok=True`.
- **TC-038** (LLR-014.1) — same shape as TC-014, redundancy ensured per the LLR/HLR split.

## 2 · Files modified (4 / 5 cap)

| Path | Change |
|------|--------|
| [app/services/mermaid.py](app/services/mermaid.py:5) | +9 lines: `from typing import Final` import, `ISO_WEEK_AXIS_TOKEN: Final[str] = "%V"` constant with rationale comment, axisFormat line changed from `%b %d` to `%b %d (W{ISO_WEEK_AXIS_TOKEN})`. |
| [tests/test_mermaid_labels.py](tests/test_mermaid_labels.py) | +5 tests + helper `_axis_format_line` + import of `ISO_WEEK_AXIS_TOKEN` and `deepcopy`. |
| [.dev-flow/01-requirements.md](.dev-flow/01-requirements.md) | LLR-009.2 acceptance updated (deepcopy + naming). LLR-014.1 statement updated (constant-based, not review-packet-based). §5.2 TC-014 / TC-030 / TC-038 rows rewritten to match. |
| [.dev-flow/change-requests-backlog.md](.dev-flow/change-requests-backlog.md) | CR-002, CR-003, CR-004 marked **CLOSED 2026-05-04 (Increment 3)** with closure evidence. Summary table now reports 3/10 closed and remaining ~70 minutes of edit work. |

4 files total — within the 5-file cap. The Increment-2 review packet correctly anticipated 3 files (`mermaid.py` + extended `test_mermaid_labels.py` + a maybe-third); the actual count grew by one because closing CRs requires updating both the requirements doc and the CR backlog. That's still in-scope per the user's "address related CRs in the same pass" direction.

## 3 · How to test

```
.venv/Scripts/python -m pytest tests/test_mermaid_labels.py -v
.venv/Scripts/python -m pytest                                          # full suite
```

## 4 · Test results

**Targeted (`tests/test_mermaid_labels.py`):**

```
============================= test session starts =============================
platform win32 -- Python 3.12.7, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\jjgh8\OneDrive\Documents\Github\ProjStatus\.claude\worktrees\zen-leavitt-f6dd3b
configfile: pyproject.toml
plugins: anyio-4.13.0
collected 10 items

tests\test_mermaid_labels.py ..........                                  [100%]

============================== 10 passed in 0.14s ==============================
```

(10 = 5 pre-existing + 5 new TCs from this increment.)

**Full suite (regression check):**

```
83 passed, 1 warning in 6.80s
```

Pre-Increment-3 baseline was 78 tests. +5 → 83. No new warnings; the single existing warning (Pydantic enum serializer in `tests/test_subtasks.py`) is unaffected by this increment.

## 5 · Risks

1. **`%V` rendering on the pinned Mermaid version.** LLR-014.1's design now allows a one-line constant change to switch to a fallback token (`%U` or another) if the pinned Mermaid CDN renders `%V` literally rather than as a week number. The current value `"%V"` is the standard ISO 8601 strftime directive and Mermaid's Gantt accepts strftime-style tokens; the verification is a phase-4 manual UAT step (see R-007). If `%V` fails, switching to a fallback is a single-character edit + re-run of `test_mermaid_labels.py`.
2. **`render_timeline` still defaults `task.start_date=None` to today.** Pre-existing behavior, untouched by this increment. Flagged in Increment 2 as a future consideration; out of scope here. The round-trip stability tests (TC-030) work because the test fixture has all dates set explicitly.
3. **No CR-008 closure.** TC-035 compound-TC pass semantics (CR-008, LOW, phase 4 due) is not relevant to this Mermaid-axis increment — it concerns LLR-013.1 testing, which lives in a future writable-peers increment.

## 6 · Pending items

The following remain explicitly **NOT covered** by this increment:

- US-002 LLRs — peer-roots config schema (LLR-001.1, -001.2, -002.1) and storage gating (LLR-003.1, -003.2, -003.3) and writable-peer guardrails (LLR-012.1).
- US-003 LLRs — actor attribution (LLR-004.1), inbox merge (LLR-005.1, -005.2, -005.3), identity gate (LLR-013.1, -013.2, -013.3).
- US-005 LLRs — Settings page (LLR-010.1, -010.2, -011.1).
- Open CRs — CR-001 (HIGH), CR-005, CR-006, CR-007, CR-008, CR-009, CR-010.

## 7 · Suggested next task

**Increment 4 — Peer-root config schema with writable flag.**

- Scope: LLR-001.1 (`_resolve_peer_roots` returns `(label, path, writable)` triples) + LLR-001.2 (Settings dataclass propagation) + LLR-002.1 (default `writable=False` when key missing).
- Files (estimated 3): `app/settings.py`, `app/main.py` (state plumbing — already partially done in Increment 1's import addition), `tests/test_peer_roots_config.py` (NEW).
- TCs: TC-001 (HLR-001 behavioural), TC-002 (HLR-002 default-false behavioural), TC-015 (LLR-001.1), TC-016 (LLR-001.2), TC-017 (LLR-002.1 missing key).
- Dependencies: none — purely config-schema work.
- CRs touched: none.
- Estimated effort: ~25 minutes.

After Increment 4, Increment 5 will tackle storage gating + canonicalization + writable-peer guardrails (LLR-003.1 + LLR-003.2 + LLR-003.3 + HLR-012/LLR-012.1) — that's a security-heavy increment and fits within the 5-file cap.

---

**Stop.** Increment 3 is complete. No Increment 4 work has begun. Awaiting user approval before proceeding.
