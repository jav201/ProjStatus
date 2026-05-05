# Validation — ProjStatus — Batch 2026-05-04-batch-01

**Phase:** 4 · **Date:** 2026-05-05 · **Validator:** orchestrator (qa-reviewer scope)

> Phase 4 executes the validation strategy defined in `.dev-flow/01-requirements.md` §5.2.
> Every HLR and LLR has at least one TC; every TC has a pass/fail evidence record below.

---

## 1 · Executive summary

| Metric | Value |
|---|---|
| HLRs validated | **14 / 14** |
| LLRs validated | **24 / 24** |
| TCs executed | **38 / 38** |
| TCs **PASS** | **38** |
| TCs **FAIL** | **0** |
| TCs **PENDING (manual UAT)** | **1** (LLR-014.1's Mermaid-CDN render verification — see §5) |
| Validation method distribution observed | test (unit) = 19 · test (integration) = 18 · inspection = 1 · demo = 0 · analysis = 0 |
| Full pytest suite | **138 passed, 1 (pre-existing) warning** in 9.49s |
| Regressions vs. main branch | **0** |
| Open CRs deferred to phase 5/6 | 5 (CR-006 MEDIUM, CR-007/-008/-009/-010 LOW) |

**Verdict:** No blocker fails. One TC (TC-038's conditional `%V` clause) pending a phase-4 manual UAT step that pytest cannot prove on its own. **Phase-4 gate ready for user decision.**

---

## 2 · Test-suite execution evidence

```
============================= test session starts =============================
platform win32 -- Python 3.12.7, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\jjgh8\OneDrive\Documents\Github\ProjStatus\.claude\worktrees\zen-leavitt-f6dd3b
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0
collected 138 items

tests\test_aggregates.py .......                                         [  5%]
tests\test_changelog.py ....                                             [  7%]
tests\test_document_render.py .....                                      [ 11%]
tests\test_identity_gate.py ....                                         [ 14%]
tests\test_inbox_attribution.py .....                                    [ 18%]
tests\test_input_sanitization.py ..................                      [ 31%]
tests\test_iso_week_label.py .........                                   [ 37%]
tests\test_mermaid_labels.py ..........                                  [ 44%]
tests\test_peer_inbox.py ....                                            [ 47%]
tests\test_peer_roots_config.py ...........                              [ 55%]
tests\test_routes.py ......                                              [ 60%]
tests\test_settings.py .....                                             [ 63%]
tests\test_settings_page.py ..........                                   [ 71%]
tests\test_storage.py .........                                          [ 77%]
tests\test_subtasks.py ................                                  [ 89%]
tests\test_week_chip_rendering.py ........                               [ 94%]
tests\test_writable_peers.py .......                                     [100%]

======================= 138 passed, 1 warning in 9.49s ========================
```

The single warning is `tests/test_subtasks.py::test_task_update_route_persists_subtasks` Pydantic-serializer warning — pre-existing on `main`, untouched by this batch.

---

## 3 · Coverage table — pass/fail per TC

> **Convention:** TC-001..TC-014 are HLR-level behavioural acceptance TCs. TC-015..TC-038 are LLR-level implementation-detail TCs. A single test function may cover one TC; a parametrized test (`pytest.mark.parametrize`) counts as multiple invocations all rolling up to the same TC ID.

### 3.1 HLR-level TCs

| TC | HLR | Method | Evidence (test function) | Status |
|----|-----|--------|--------------------------|--------|
| TC-001 | HLR-001 | test (unit) | `tests/test_peer_roots_config.py::test_tc_001_writable_true_preserved_from_toml` | ✅ PASS |
| TC-002 | HLR-002 | test (unit) | `tests/test_peer_roots_config.py::test_tc_002_writable_defaults_false_when_omitted` | ✅ PASS |
| TC-003 | HLR-003 | test (integration) | `tests/test_writable_peers.py::test_tc_003_non_writable_peer_save_rejected` | ✅ PASS |
| TC-004 | HLR-004 | test (integration) | covered by `tests/test_inbox_attribution.py::test_tc_021_writable_peer_records_local_actor` (HLR-004 = LLR-004.1 behavioural + impl. — single integration test exercises both) | ✅ PASS |
| TC-005 | HLR-005 | test (integration) | `tests/test_inbox_attribution.py::test_tc_005_writable_peer_addendum_surfaces_in_inbox` | ✅ PASS |
| TC-006 | HLR-006 | test (unit) | `tests/test_iso_week_label.py::test_iso_week_label_w18` | ✅ PASS |
| TC-007 | HLR-007 | test (integration) | `tests/test_week_chip_rendering.py::test_tc_007_task_card_renders_w18_for_2026_04_27` | ✅ PASS |
| TC-008 | HLR-008 | test (integration) | `tests/test_week_chip_rendering.py::test_tc_008_milestone_renders_w19_for_2026_05_04` | ✅ PASS |
| TC-009 | HLR-009 | test (unit) | `tests/test_mermaid_labels.py::test_tc_009_render_timeline_axis_contains_week_token` | ✅ PASS |
| TC-010 | HLR-010 | test (integration) | `tests/test_settings_page.py::test_tc_010_get_settings_renders_all_state` + `::test_tc_010_sidebar_link_to_settings_present` | ✅ PASS |
| TC-011 | HLR-011 | test (integration) | `tests/test_settings_page.py::test_tc_011_and_tc_033_mutating_methods_return_405[POST/PUT/PATCH/DELETE]` (4 parametrized cases) | ✅ PASS |
| TC-012 | HLR-012 | test (integration) | `tests/test_writable_peers.py::test_tc_012_root_writable_demoted` | ✅ PASS |
| TC-013 | HLR-013 | test (integration) | `tests/test_identity_gate.py::test_tc_013_writable_peer_raises_data_root_succeeds` | ✅ PASS |
| TC-014 | HLR-014 | test (unit) | `tests/test_mermaid_labels.py::test_tc_014_axis_has_w_and_roundtrip_ok` | ✅ PASS (conditional `%V` clause: see §5) |

### 3.2 LLR-level TCs

| TC | LLR | Method | Evidence (test function) | Status |
|----|-----|--------|--------------------------|--------|
| TC-015 | LLR-001.1 | test (unit) | `tests/test_peer_roots_config.py::test_tc_015_resolve_peer_roots_triple_shape` | ✅ PASS |
| TC-016 | LLR-001.2 | test (unit) | `tests/test_peer_roots_config.py::test_tc_016_app_state_peer_roots_shape` | ✅ PASS |
| TC-017 | LLR-002.1 | test (unit) | `tests/test_peer_roots_config.py::test_tc_017_writable_coerces_to_false_when_not_bool[7 parametrized cases]` | ✅ PASS |
| TC-018 | LLR-003.1 | test (unit) | `tests/test_writable_peers.py::test_tc_018_save_outside_writable_roots_raises` | ✅ PASS |
| TC-019 | LLR-003.2 | test (unit) | `tests/test_writable_peers.py::test_tc_019_storage_service_accepts_writable_roots_kwarg` | ✅ PASS |
| TC-020 | LLR-003.3 | test (integration) | `tests/test_writable_peers.py::test_tc_020_canonicalization_rejects_dotdot_escape` + `::test_tc_020_canonicalization_rejects_symlink_escape` | ✅ PASS (symlink half skipped on Windows-without-Developer-Mode per §5.4.C) |
| TC-021 | LLR-004.1 | test (integration) | `tests/test_inbox_attribution.py::test_tc_021_writable_peer_records_local_actor` | ✅ PASS |
| TC-022 | LLR-005.1 | test (unit) | `tests/test_inbox_attribution.py::test_tc_022_read_peer_addendums_iterates_regardless_of_writable_flag` | ✅ PASS |
| TC-023 | LLR-005.2 | test (unit) | `tests/test_inbox_attribution.py::test_tc_023_throwaway_storage_service_is_non_writable` | ✅ PASS |
| TC-024 | LLR-005.3 | test (integration) | `tests/test_inbox_attribution.py::test_tc_024_peer_row_renders_claimed_qualifier` | ✅ PASS |
| TC-025 | LLR-006.1 | test (unit) | `tests/test_iso_week_label.py::test_iso_week_label_boundaries[6 parametrized cases]` + `::test_iso_week_label_none_returns_empty` | ✅ PASS |
| TC-026 | LLR-007.1 | test (integration) | `tests/test_week_chip_rendering.py::test_tc_026_task_card_fixtures[4 parametrized cases]` + `::test_tc_026_no_start_date_renders_no_chip` | ✅ PASS |
| TC-027 | LLR-007.2 | test (integration) | `tests/test_iso_week_label.py::test_iso_week_label_registered_as_jinja_global` | ✅ PASS |
| TC-028 | LLR-008.1 | test (integration) | `tests/test_week_chip_rendering.py::test_tc_028_milestone_no_target_date_renders_no_chip` | ✅ PASS |
| TC-029 | LLR-009.1 | test (unit) | `tests/test_mermaid_labels.py::test_tc_029_w_only_on_axis_format_line` | ✅ PASS |
| TC-030 | LLR-009.2 | test (unit) | `tests/test_mermaid_labels.py::test_tc_030_roundtrip_byte_identical_via_deepcopy` | ✅ PASS (deepcopy round-trip — CR-002 closure verified) |
| TC-031 | LLR-010.1 | test (integration) | `tests/test_settings_page.py::test_tc_031_peer_rows_render_rw_ro_and_unreachable` + `::test_tc_031_read_only_peer_renders_ro` | ✅ PASS |
| TC-032 | LLR-010.2 | inspection | `tests/test_settings_page.py::test_tc_032_settings_template_is_non_mutating` (source-level grep against `app/templates/settings.html`) | ✅ PASS |
| TC-033 | LLR-011.1 | test (integration) | `tests/test_settings_page.py::test_tc_011_and_tc_033_mutating_methods_return_405[…]` + `::test_tc_033_no_mutating_handler_registered` | ✅ PASS |
| TC-034 | LLR-012.1 | test (unit) | `tests/test_writable_peers.py::test_tc_034_demotion_branches_and_warn_once` | ✅ PASS |
| TC-035 | LLR-013.1 | test (integration) | `tests/test_identity_gate.py::test_tc_035a_writable_peer_unknown_actor_rejected` + `::test_tc_035b_data_root_unknown_actor_succeeds` + `::test_tc_035c_non_writable_peer_unknown_actor_writability_error` | ✅ PASS (3 sub-cases) |
| TC-036 | LLR-013.2 | test (unit) | `tests/test_input_sanitization.py::test_tc_036_*` (7 functions covering env fall-through, length cap, null-byte strip, U+202E RLO, parametrized zero-width fixtures, sanitizer-never-returns-unknown) | ✅ PASS |
| TC-037 | LLR-013.3 | test (unit) | `tests/test_input_sanitization.py::test_tc_037_*` (8 functions covering markdown-link escape, HTML-tag escape, **CR-001 entity-bypass round-trip**, newline collapse, pipe escape, post-escape cap-at-200, thousand-newline regression, on-disk integration) | ✅ PASS |
| TC-038 | LLR-014.1 | test (unit) | `tests/test_mermaid_labels.py::test_tc_038_fallback_token_assertion_is_conditional` | ✅ PASS (always-on assertions); manual UAT pending for browser render — see §5 |

---

## 4 · Method-distribution audit

The §5.2 coverage table claims **19 unit + 18 integration + 1 inspection = 38**. Independent recount of the table rows during phase 4 produces:

- **test (unit):** TC-001, TC-002, TC-006, TC-009, TC-014, TC-015, TC-016, TC-017, TC-018, TC-019, TC-022, TC-023, TC-025, TC-029, TC-030, TC-034, TC-036, TC-037, TC-038 = **19** ✓
- **test (integration):** TC-003, TC-004, TC-005, TC-007, TC-008, TC-010, TC-011, TC-012, TC-013, TC-020, TC-021, TC-024, TC-026, TC-027, TC-028, TC-031, TC-033, TC-035 = **18** ✓
- **inspection:** TC-032 = **1** ✓
- **demo / analysis / e2e:** 0 ✓

Total: **38** ✓.

---

## 5 · Pending items / gaps

### 5.1 LLR-014.1 — manual UAT for Mermaid `%V` rendering

- **Status:** **PENDING UAT**
- **Source:** §5.2 TC-038 + §6.3 R-005.
- **What pytest verifies (already PASS):**
  - The `axisFormat` line of `render_timeline(p)` contains the literal `W`.
  - `import_timeline(p, render_timeline(p))[3] is True` (round-trip ok flag).
  - The constant `ISO_WEEK_AXIS_TOKEN = "%V"` is exported and used by both source and tests.
- **What pytest CANNOT verify:**
  - Whether the Mermaid CDN version pinned by `app/templates/base.html` actually renders the `%V` strftime directive as a literal week number (`W17`, `W18`, …) in the browser SVG, vs. emitting the literal text `(W%V)`.
- **How to verify (manual UAT):**
  1. Start the dev server: `python -m uvicorn app.main:app --reload`.
  2. Open any project's Gantt page in a browser (`/projects/<slug>/timeline`).
  3. Inspect the rendered Mermaid axis. The week labels MUST appear as `Wnn` (e.g., `Apr 26 (W17)`), NOT as the literal text `(W%V)`.
  4. If `%V` renders literally, change `ISO_WEEK_AXIS_TOKEN = "%V"` → `"%U"` (or another supported token) in `app/services/mermaid.py`, re-run `pytest tests/test_mermaid_labels.py` (TC-038's conditional `%V`-absence assertion will then fire), and re-run UAT.
- **Recommended owner:** any reviewer with browser access. Estimated effort: 5 minutes.

### 5.2 Pre-existing Pydantic-serializer warning (not introduced by this batch)

`tests/test_subtasks.py::test_task_update_route_persists_subtasks` emits a `PydanticSerializationUnexpectedValue` warning about `field_name='priority', input_value='medium', input_type=str`. This existed on `main` before the batch; not in scope for phase 4. Worth flagging for phase-5 retrospective as a candidate cleanup.

### 5.3 Pre-existing `render_timeline` defaulting `task.start_date=None` to today

Discovered during Increment 2; documented in §5 of `increment-002.md`. Not in scope for this batch. The negative-chip TC-026 case bypasses the route round-trip and tests the template condition directly via Jinja env.

### 5.4 Open CRs (deferred to phase 5/6 per the user's explicit deferral decision)

| CR | Severity | Status | Disposition |
|----|----------|--------|-------------|
| CR-006 | MEDIUM | open | Add venv/site-packages paths to LLR-012.1 demotion list. Phase-5 candidate. |
| CR-007 | LOW | open | `actor="unknown"` peer-visible carve-out documentation. Phase-5 candidate. |
| CR-008 | LOW | open | TC-035 compound-TC pass semantics — already mitigated by separate `test_tc_035a/b/c` test functions; explicit §5.3 line still TBD. Phase-5 candidate. |
| CR-009 | LOW | open | `.gitignore` recommendation for `config.toml` in USER_GUIDE.md. Phase-6 (docs) candidate. |
| CR-010 | LOW | open | 12 deferred minors bundled. Phase-6 candidate. |

None of these block the phase-4 gate; they were explicitly deferred during phase-2 iteration-3 with user approval.

---

## 6 · §5.3 batch acceptance criteria check

| Criterion | Result |
|---|---|
| 100% of LLRs covered by at least one TC with `pass` result | ✅ 24/24 |
| 0 blocker fails in validation | ✅ |
| Every HLR and LLR has an assigned validation method | ✅ |
| `grep should` inside any HLR-/LLR-statement line returns zero | ✅ (verified by phase-2 iter-3 closure check) |
| Locked design decisions in §6.2 each map to either an HLR or §2.5 assumption | ✅ (D-001 → HLR-001/002 + A-006; D-002 → HLR-010/-011 + A-005; D-003 → HLR-006 + A-004; D-004 → HLR-009 + LLR-009.1/-009.2; D-005 → HLR-004 + A-003 + A-010) |
| Per-TC self-contained fixtures (`tmp_path` + `monkeypatch.setenv`); no cross-TC dependencies | ✅ (verified during increment 5 / 6a / 6b — every new test uses `tmp_path` + `monkeypatch`) |
| Method distribution adds up: 19 unit + 18 integration + 1 inspection = 38 = 14 HLR + 24 LLR | ✅ |

All 7 criteria pass.

---

## 7 · Verdict

**Phase 4 PASS — no blocker fails.** All 38 TCs pass. One TC (TC-038) has a manual UAT pending step that pytest cannot verify on its own; this is documented as **R-005** in `01-requirements.md` §6.3 and is a process check the user can run in 5 minutes against the live dev server.

**Recommended next:** advance to phase 5 (post-mortem) with the manual UAT either completed or formally deferred to phase 6 / a follow-up batch.

**Phase-4 gate ready for user decision.**
