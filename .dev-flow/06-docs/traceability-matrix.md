# Traceability Matrix — ProjStatus — Batch 2026-05-04-batch-01

> Full chain: **User Story → HLR → LLR → Test Case → File:line**.
> Closed at end of phase 6. All 38 TCs verified `pass` in phase 4 (`.dev-flow/04-validation.md`).
>
> **TC convention:** TC-001..TC-014 are HLR-level behavioural acceptance TCs; TC-015..TC-038 are LLR-level implementation-detail TCs. The two layers are complementary — neither is redundant.

---

## 1 · Master table

| US     | HLR     | LLR       | TC     | Test function | Implementation file:line | Status  |
|--------|---------|-----------|--------|---------------|--------------------------|---------|
| US-001 | (none — already implemented in PR #18) | — | — | (existing tests in `tests/test_peer_inbox.py`, `tests/test_storage.py`) | `app/settings.py` (existing) | n/a |
| US-002 | HLR-001 | — | TC-001 | `test_peer_roots_config.py::test_tc_001_writable_true_preserved_from_toml` | `app/settings.py:62` (`_resolve_peer_roots`) | **pass** |
| US-002 | HLR-001 | LLR-001.1 | TC-015 | `test_peer_roots_config.py::test_tc_015_resolve_peer_roots_triple_shape` | `app/settings.py:62-78` | **pass** |
| US-002 | HLR-001 | LLR-001.2 | TC-016 | `test_peer_roots_config.py::test_tc_016_app_state_peer_roots_shape` | `app/settings.py:155` (`Settings` dataclass), `app/main.py:79` (`app.state.peer_roots`) | **pass** |
| US-002 | HLR-002 | — | TC-002 | `test_peer_roots_config.py::test_tc_002_writable_defaults_false_when_omitted` | `app/settings.py:75` (`writable = entry.get("writable", False) is True`) | **pass** |
| US-002 | HLR-002 | LLR-002.1 | TC-017 | `test_peer_roots_config.py::test_tc_017_writable_coerces_to_false_when_not_bool` | `app/settings.py:75` | **pass** |
| US-002 | HLR-003 | — | TC-003 | `test_writable_peers.py::test_tc_003_non_writable_peer_save_rejected` | `app/services/storage.py:474-489` (`_check_writable`) | **pass** |
| US-002 | HLR-003 | LLR-003.1 | TC-018 | `test_writable_peers.py::test_tc_018_save_outside_writable_roots_raises` | `app/services/storage.py:474-489` | **pass** |
| US-002 | HLR-003 | LLR-003.2 | TC-019 | `test_writable_peers.py::test_tc_019_storage_service_accepts_writable_roots_kwarg` | `app/services/storage.py:84-101` (`StorageService.__init__`) | **pass** |
| US-002 | HLR-003 | LLR-003.3 | TC-020 | `test_writable_peers.py::test_tc_020_canonicalization_rejects_dotdot_escape` + `::test_tc_020_canonicalization_rejects_symlink_escape` | `app/services/storage.py:476-489` (`Path.resolve` + `is_relative_to`) | **pass** (symlink half skipped on Windows-without-Developer-Mode) |
| US-002 | HLR-012 | — | TC-012 | `test_writable_peers.py::test_tc_012_root_writable_demoted` | `app/settings.py:140` (`_demote_dangerous_writable_peers`) | **pass** |
| US-002 | HLR-012 | LLR-012.1 | TC-034 | `test_writable_peers.py::test_tc_034_demotion_branches_and_warn_once` | `app/settings.py:90-138` (`_dangerous_writable_predicate`) + `:140` (post-pass) | **pass** |
| US-003 | HLR-004 | — | TC-004 | `test_inbox_attribution.py::test_tc_021_writable_peer_records_local_actor` | `app/services/storage.py:526` (`actor` passthrough in `save_project`) | **pass** |
| US-003 | HLR-004 | LLR-004.1 | TC-021 | (same as TC-004) | `app/main.py` route handlers passing `actor=current_actor(request)` | **pass** |
| US-003 | HLR-005 | — | TC-005 | `test_inbox_attribution.py::test_tc_005_writable_peer_addendum_surfaces_in_inbox` | `app/services/storage.py:763-790` (`read_peer_addendums`), `app/templates/inbox.html` | **pass** |
| US-003 | HLR-005 | LLR-005.1 | TC-022 | `test_inbox_attribution.py::test_tc_022_read_peer_addendums_iterates_regardless_of_writable_flag` | `app/services/storage.py:773` (loop ignores `writable`) | **pass** |
| US-003 | HLR-005 | LLR-005.2 | TC-023 | `test_inbox_attribution.py::test_tc_023_throwaway_storage_service_is_non_writable` | `app/services/storage.py:783-786` (`StorageService(peer_config, writable_roots=[])`) | **pass** |
| US-003 | HLR-005 | LLR-005.3 | TC-024 | `test_inbox_attribution.py::test_tc_024_peer_row_renders_claimed_qualifier` | `app/templates/inbox.html:32-38` (peer-row markup with `(claimed)`) | **pass** |
| US-003 | HLR-013 | — | TC-013 | `test_identity_gate.py::test_tc_013_writable_peer_raises_data_root_succeeds` | `app/services/storage.py:491-510` (`_check_actor_for_peer_write`) | **pass** |
| US-003 | HLR-013 | LLR-013.1 | TC-035 | `test_identity_gate.py::test_tc_035a_*` + `::test_tc_035b_*` + `::test_tc_035c_*` | `app/services/storage.py:491-510` | **pass** (3 sub-cases) |
| US-003 | HLR-013 | LLR-013.2 | TC-036 | `test_input_sanitization.py::test_tc_036_*` (7 functions) | `app/settings.py:18-50` (`_USER_STRIP_CHARS`, `_sanitize_user_candidate`, `_resolve_user`) | **pass** |
| US-003 | HLR-013 | LLR-013.3 | TC-037 | `test_input_sanitization.py::test_tc_037_*` (8 functions) | `app/services/storage.py:65-89` (`_CHANGELOG_FIELD_MAX_LEN`, `_sanitize_changelog_field`, `_append_changelog`) | **pass** (CR-001 entity-bypass closure verified) |
| US-004 | HLR-006 | — | TC-006 | `test_iso_week_label.py::test_iso_week_label_w18` | `app/utils.py:42-45` (`iso_week_label`) | **pass** |
| US-004 | HLR-006 | LLR-006.1 | TC-025 | `test_iso_week_label.py::test_iso_week_label_boundaries[6 cases]` + `::test_iso_week_label_none_returns_empty` | `app/utils.py:42-45` | **pass** |
| US-004 | HLR-007 | — | TC-007 | `test_week_chip_rendering.py::test_tc_007_task_card_renders_w18_for_2026_04_27` | `app/templates/partials/project_board.html:23` (`<span class="week-chip">`) | **pass** |
| US-004 | HLR-007 | LLR-007.1 | TC-026 | `test_week_chip_rendering.py::test_tc_026_task_card_fixtures[4 cases]` + `::test_tc_026_no_start_date_renders_no_chip` | `app/templates/partials/project_board.html:23` | **pass** |
| US-004 | HLR-007 | LLR-007.2 | TC-027 | `test_iso_week_label.py::test_iso_week_label_registered_as_jinja_global` | `app/main.py:72` (`templates.env.globals["iso_week_label"] = iso_week_label`) | **pass** |
| US-004 | HLR-008 | — | TC-008 | `test_week_chip_rendering.py::test_tc_008_milestone_renders_w19_for_2026_05_04` | `app/templates/partials/_milestones_list.html:21` | **pass** |
| US-004 | HLR-008 | LLR-008.1 | TC-028 | `test_week_chip_rendering.py::test_tc_028_milestone_no_target_date_renders_no_chip` | `app/templates/partials/_milestones_list.html:21` | **pass** |
| US-004 | HLR-009 | — | TC-009 | `test_mermaid_labels.py::test_tc_009_render_timeline_axis_contains_week_token` | `app/services/mermaid.py:43-44` (`axisFormat %b %d (W%V)`) | **pass** |
| US-004 | HLR-009 | LLR-009.1 | TC-029 | `test_mermaid_labels.py::test_tc_029_w_only_on_axis_format_line` | `app/services/mermaid.py:51` (axisFormat line in `render_timeline`) | **pass** |
| US-004 | HLR-009 | LLR-009.2 | TC-030 | `test_mermaid_labels.py::test_tc_030_roundtrip_byte_identical_via_deepcopy` | `app/services/mermaid.py:90-156` (`import_timeline`) | **pass** (CR-002 deepcopy round-trip closure) |
| US-004 | HLR-014 | — | TC-014 | `test_mermaid_labels.py::test_tc_014_axis_has_w_and_roundtrip_ok` | `app/services/mermaid.py:11` (`ISO_WEEK_AXIS_TOKEN: Final[str] = "%V"`) | **pass** |
| US-004 | HLR-014 | LLR-014.1 | TC-038 | `test_mermaid_labels.py::test_tc_038_fallback_token_assertion_is_conditional` | `app/services/mermaid.py:11`, `tests/test_mermaid_labels.py:96-110` | **pass** (manual UAT pending — see §3 G-007) |
| US-005 | HLR-010 | — | TC-010 | `test_settings_page.py::test_tc_010_get_settings_renders_all_state` + `::test_tc_010_sidebar_link_to_settings_present` | `app/main.py:248-280` (`@app.get("/settings")`), `app/templates/settings.html`, `app/templates/base.html:56-58` | **pass** |
| US-005 | HLR-010 | LLR-010.1 | TC-031 | `test_settings_page.py::test_tc_031_peer_rows_render_rw_ro_and_unreachable` + `::test_tc_031_read_only_peer_renders_ro` | `app/main.py:248-280`, `app/templates/settings.html:35-50` | **pass** |
| US-005 | HLR-010 | LLR-010.2 | TC-032 | `test_settings_page.py::test_tc_032_settings_template_is_non_mutating` | `app/templates/settings.html` (entire file — non-mutating invariant) | **pass** (inspection) |
| US-005 | HLR-011 | — | TC-011 | `test_settings_page.py::test_tc_011_and_tc_033_mutating_methods_return_405[POST/PUT/PATCH/DELETE]` | `app/main.py:248` (only `@app.get` registered for `/settings`) | **pass** (4 parametrized) |
| US-005 | HLR-011 | LLR-011.1 | TC-033 | `test_settings_page.py::test_tc_011_and_tc_033_mutating_methods_return_405[…]` + `::test_tc_033_no_mutating_handler_registered` | `app/main.py:248` | **pass** |

---

## 2 · Coverage summary

| Metric | Value |
|--------|-------|
| Total user stories | 5 |
| User stories with HLR coverage in this batch | 4 (US-002, US-003, US-004, US-005) |
| User stories already covered by prior work | 1 (US-001 — PR #18) |
| Total HLR | 14 |
| Implemented HLR | **14 / 14** ✅ |
| Total LLR | 24 |
| Implemented LLR | **24 / 24** ✅ |
| Test cases planned | 38 |
| **TC pass** | **38** |
| TC fail | 0 |
| TC pending (manual UAT) | 1 (TC-038's `%V`-render UAT — automated assertions PASS, browser-render check is the manual portion) |

**Validation method distribution (final):** test (unit) = 19 · test (integration) = 18 · inspection = 1 · demo = 0 · analysis = 0 · test (e2e) = 0.

---

## 3 · Detected gaps

> Final state at end of phase 5.

| ID | Type | Description | Status / proposed action |
|----|------|-------------|--------------------------|
| G-001 | scope (closed) | US-001 already implemented in PR #18; no new HLR. | Closed — surface confirmation delivered via US-005 (Settings page). |
| G-002 | resolved | Multi-week task display rule was open at start of phase 1. | Resolved — option (b): `Wnn` when same ISO week, `Wnn–Wmm` when they differ. |
| G-003 | resolved | Mermaid `axisFormat` token compatibility (`%V`) was an unbound risk. | Resolved by HLR-014 / LLR-014.1 + `ISO_WEEK_AXIS_TOKEN` constant (CR-003 closure). Manual UAT remains for browser-render confirmation (G-007). |
| G-004 | reduced | Settings reachability used `Path.exists()` only. | Reduced via LLR-010.1's switch to `Path.is_dir()` + `os.path.realpath` containment. Full read-probe deferred to a future batch. |
| G-005 | non-verifiable | A-001 ("ProjStatus does not perform a permission check beyond attempting the write") is a negative claim about absent code. | Resolved via inspection of `save_project` path during phase 2 review. |
| G-006 | resolved | Phase-1 v1 had `actor="unknown"` writes silently allowed against peer roots. | Resolved by HLR-013 / LLR-013.1 (B-003). |
| G-007 | resolved | Phase-1 v1 had no path canonicalization on the writable-roots check. | Resolved by LLR-003.3 (Path.resolve + is_relative_to). |
| G-008 | resolved | Phase-1 v1 had no defensive guardrails on writable peer paths. | Resolved by HLR-012 / LLR-012.1 — 13 dangerous-path predicates. |
| G-009 | open (manual UAT) | No e2e/visual harness — visual TCs verified only by HTML substring. TC-038's `%V`-renders-as-`Wnn` browser check is a 5-minute manual step. | Mitigated via R-007. Recommended next-batch closure via Playwright (post-mortem item 1). |
| G-010 | acknowledged | Two-people-one-OS-login attribution (A-009 / R-009). | Out of scope; phase-5 retrospective notes it. |
| G-011 | resolved | Phase-2 iteration-2 found LLR-009.2 example used a non-existent API surface (B-006). | Resolved in phase-1 iteration 3 — LLR-009.2 acceptance now uses real `import_timeline(project, text) -> 4-tuple` signature. |
| G-012 | resolved | Phase-2 iteration-2 found TC-038 / LLR-014.1 self-contradicting on `%V` (B-Q-001). | Resolved — `%V`-absence assertion now CONDITIONAL on the `ISO_WEEK_AXIS_TOKEN` constant value. |
| G-013 | resolved | HLR-012 demotion list missed sensitive home-dir CHILDREN (N-S-002). | Resolved — LLR-012.1 now demotes paths equal to or under `~/.ssh`, `~/.aws`, `~/.config`, `~/.gnupg`, `~/.kube`, `~/.docker`, `/etc`, `/usr`, `/var`, `/bin`, `/sbin` (POSIX) and `%APPDATA%`, `%LOCALAPPDATA%`, `%PROGRAMDATA%` (Windows). |

---

## 4 · Changes from previous batch

*(First `.dev-flow/` batch on this repo — nothing to compare yet.)*

| Type | Item | Detail |
|------|------|--------|
| new | All artifacts | First `.dev-flow/` batch on ProjStatus. |

---

## 5 · Quick bidirectional mapping

### 5.1 By user story

- **US-001** → (no HLR — already implemented in PR #18; existing tests in `test_peer_inbox.py` and `test_storage.py`)
- **US-002** → HLR-001, HLR-002, HLR-003, HLR-012 → LLR-001.1, LLR-001.2, LLR-002.1, LLR-003.1, LLR-003.2, LLR-003.3, LLR-012.1 → TC-001, TC-002, TC-003, TC-012, TC-015, TC-016, TC-017, TC-018, TC-019, TC-020, TC-034
- **US-003** → HLR-004, HLR-005, HLR-013 → LLR-004.1, LLR-005.1, LLR-005.2, LLR-005.3, LLR-013.1, LLR-013.2, LLR-013.3 → TC-004, TC-005, TC-013, TC-021, TC-022, TC-023, TC-024, TC-035, TC-036, TC-037
- **US-004** → HLR-006, HLR-007, HLR-008, HLR-009, HLR-014 → LLR-006.1, LLR-007.1, LLR-007.2, LLR-008.1, LLR-009.1, LLR-009.2, LLR-014.1 → TC-006, TC-007, TC-008, TC-009, TC-014, TC-025, TC-026, TC-027, TC-028, TC-029, TC-030, TC-038
- **US-005** → HLR-010, HLR-011 → LLR-010.1, LLR-010.2, LLR-011.1 → TC-010, TC-011, TC-031, TC-032, TC-033

### 5.2 By code file

- `app/settings.py` → LLR-001.1, LLR-001.2, LLR-002.1, LLR-012.1, LLR-013.2
- `app/services/storage.py` → LLR-003.1, LLR-003.2, LLR-003.3, LLR-004.1, LLR-005.1, LLR-005.2, LLR-013.1, LLR-013.3 (+ new `PeerWriteForbidden` exception class)
- `app/services/mermaid.py` → LLR-009.1, LLR-009.2, LLR-014.1 (+ new `ISO_WEEK_AXIS_TOKEN` module constant)
- `app/utils.py` → LLR-006.1
- `app/main.py` → LLR-001.2, LLR-003.2, LLR-004.1, LLR-007.2, LLR-010.1, LLR-011.1
- `app/templates/partials/project_board.html` → LLR-007.1
- `app/templates/partials/_milestones_list.html` → LLR-008.1
- `app/templates/settings.html` (NEW) → LLR-010.1, LLR-010.2
- `app/templates/inbox.html` → LLR-005.3
- `app/templates/base.html` → sidebar link for Settings page (HLR-010)
- `tests/` → 9 new test files (1 modified existing): test_iso_week_label.py, test_week_chip_rendering.py, test_mermaid_labels.py (+5 tests), test_peer_roots_config.py, test_writable_peers.py, test_identity_gate.py, test_input_sanitization.py, test_inbox_attribution.py, test_settings_page.py

---

## 6 · Batch sign-off

| Field | Value |
|-------|-------|
| Batch ID | 2026-05-04-batch-01 |
| Closing date | 2026-05-05 |
| Phases iterated | P1×3, P2×3, P3×8, P4×1, P5×1, P6×1 |
| Validation passed | yes (38/38 TCs PASS; 1 manual UAT pending) |
| HIGH-severity CRs closed | 2 / 2 (CR-001 entity-bypass, CR-002 round-trip tautology) |
| All HIGH/MEDIUM CRs that gated phase 4 closed | yes (5 / 5) |
| Open CRs carried forward | 5 (1 MEDIUM CR-006, 4 LOW CR-007/-008/-009/-010) |
| Synced to Obsidian | no — pending `/dev-flow-sync-en` after PR merge |
