# Post-mortem — ProjStatus — Batch 2026-05-04-batch-01

**Phase:** 5 · **Date:** 2026-05-05 · **Co-authors:** `architect` + `qa-reviewer` (orchestrator-merged).

> Batch scope: per-peer write-mode flag for peer roots, read-only Settings page surfacing data_root/peer_roots/user, ISO 8601 calendar-week indicator on tasks/milestones/Gantt.

---

## 1 · Executive summary

| Field | Value |
|---|---|
| User stories | 5 (US-001..US-005) |
| HLRs / LLRs | 14 / 24 |
| TCs total | 38 (all PASS) + 1 manual UAT pending |
| Pytest suite | 138 passed, 1 pre-existing warning, 0 regressions |
| Phases iterated | P1 ×3, P2 ×3, P3 ×8 increments (1,2,3,4,5,6a,6b,7), P4 ×1 |
| CRs raised in phase-2 iter-2 | 26 (2 blockers + 9 majors + 15 minors) |
| CRs closed during phase 3 | 5 (CR-001 HIGH, CR-002 HIGH, CR-003 / -004 / -005 MEDIUM) |
| CRs still open at phase-4 close | 5 (1 MEDIUM, 4 LOW) |
| Net new lines (source/template/test) | ~+1100 |
| Verdict | **Phase 4 PASS** — ready for documentation (phase 6) |

---

## 2 · What worked

### Architecture / requirements lens (`architect`)

- **EARS strict `shall`/`should` discipline plus a self-review pass** caught real ambiguity. The phase-1 iteration-3 self-review (`state.json`: "Self-review clean: 0 'should' inside HLR/LLR statements; 38 unique TCs") was the gate that confirmed `_check_writable` semantics had been pinned to "shall raise `PeerWriteForbidden`" rather than the looser original wording — which is what made TC-031 / TC-033 enforceable in phase 4.
- **Splitting LLR-009.1 into LLR-009.1 + LLR-009.2 in iteration 2** was the correct decomposition. Without that split, the round-trip claim and the format claim were entangled and the CR-002 tautology would have masked a deeper semantic bug.
- **The two-tier "behavioural HLR-TC + implementation-detail LLR-TC" convention** kept the §5.2 coverage table readable. Phase 4's 38/38 PASS includes negative paths (TC-031 `unreachable`, TC-033 `PeerWriteForbidden`) and source-inspection checks (TC-032) without inflating the HLR count — "user-visible behaviour at HLR, internal contract at LLR" held throughout 14 HLRs / 24 LLRs.
- **Locked design decisions D-001..D-005** (per-peer flag in config.toml, non-mutating Settings page, ISO 8601, sanitizer chain order, A-010 actor-unknown carve-out) prevented scope drift across 8 increments. Increment 7 shipped read-only as designed in D-002 even though by then the team had touched enough Jinja that an editable surface would have been tempting.
- **The 5-file-per-increment cap held in every increment**. Increments 4 and 5 noted "5 files touched (at cap)", forcing decomposition rather than inflation. Increment 6 was the only one that needed splitting (6a + 6b), and that split was clean: 6a closed the two HIGH/MEDIUM security CRs (CR-001 entity-bypass, CR-005 zero-width Unicode) before 6b touched UI strings.
- **The CR-backlog mechanism deferred 10 non-blocker findings** without breaking the V-model. The phase-2 iteration-3 conditional-approve closed the requirements doc against 1 HIGH + 9 majors + 15 minors as named technical debt rather than triggering a 4th iteration.

### Validation / testing lens (`qa-reviewer`)

- **Per-TC self-contained `tmp_path` + `monkeypatch.setenv` discipline** (codified in §5.3 + §5.4.C) prevented all cross-TC dependencies. Every new test in `test_writable_peers.py`, `test_identity_gate.py`, `test_inbox_attribution.py`, `test_input_sanitization.py`, and `test_settings_page.py` opens with `tmp_path: Path, monkeypatch: pytest.MonkeyPatch`. Result: 138-test suite runs in ~9.5 s and is reorderable.
- **Constant-based conditional-assertion pattern for TC-038 / TC-014** (CR-003 closure): exporting `ISO_WEEK_AXIS_TOKEN: Final[str] = "%V"` from `app/services/mermaid.py` gave both tests a machine-readable signal source. The previous design (read the markdown review packet at runtime) was untestable from pytest.
- **Closing CR-002's tautological round-trip** in Increment 3 added real regression-detection capability: `test_tc_030_roundtrip_byte_identical_via_deepcopy` now passes `deepcopy(p)` into `import_timeline`, so a future bug where `import_timeline` silently no-ops would surface. Pre-fix, the assertion held vacuously because `imported is p`.
- **The Jinja-direct test pattern for TC-026** (negative case bypassing the route round-trip) was an honest workaround for the pre-existing `render_timeline` `None`→today defaulting flagged in Increment 2.
- **The deferred-CR mechanism + the backlog file as sole tracking surface** prevented an infinite review loop and prevented parallel TODO drift across `02-review.md` and the increments.

---

## 3 · What didn't work / friction

### Architecture / requirements lens

- **Phase-2 iteration-2 found 2 NEW blockers (B-006 LLR-009.2 wrong `import_timeline` API, B-Q-001 TC-038 self-contradicting `%V` assertion)** that the iteration-1 fixes introduced. The iter-1 patches were authored without re-grounding against `app/services/mermaid.py::import_timeline`'s actual return signature `(project, imported_msgs, errors, supported)`. **Lesson:** iteration-N fixes need a re-grounding pass against the named code symbol before the iteration-N+1 review.
- **HLR-013 (actor-required peer writes) needed carve-out A-010** because requiring `PROJSTATUS_USER` for *all* writes broke unconfigured single-user machines. The carve-out is correct but means the requirement is no longer monotonic — there are now two write modes with different actor rules. CR-007 captures the documentation gap.
- **Increment 2 surfaced a pre-existing `render_timeline` None→today defaulting** for tasks with no `start`/`end` dates. It blocked TC-026's negative path through the route. Out of scope but architecturally hot — `render_timeline` should fail loudly or skip the row, not silently substitute today.
- **LLR-005.1 was verified-only with no code change needed** (Increment 6b: "pre-existing behavior conforms"). Same with LLR-004.1's relationship to existing `read_peer_addendums`. The requirements doc was somewhat over-prescriptive: writing LLRs for behaviour the codebase already exhibits inflates the doc and the TC count without changing the implementation surface.

### Validation / testing lens

- **Pytest's `tmp_path` on Windows lives under `%LOCALAPPDATA%`, which trips LLR-012.1's demotion predicate.** Every test that constructs `Settings.load()` with `tmp_path`-based `data_root` had to call a `_strip_windows_env(monkeypatch)` helper. Confirmed in 4 files: `test_writable_peers.py`, `test_inbox_attribution.py`, `test_identity_gate.py`, `test_settings_page.py`. The LLR predicate is correct in production but hostile to tests — **architectural smell**: the predicate operates on `os.environ` at load time, not at config-parse time, which makes it test-environment-coupled.
- **TC-038's conditional `%V`-absence assertion was reworked twice** (phase-2 iter-2 → iter-3) before the constant-based design landed. Each rework consumed a review-iteration slot.
- **LLR-009.2's tautological round-trip (CR-002) wasn't caught until phase-2 iter-3.** The architect's iter-2 review missed that `import_timeline` mutates in place and returns the same object. **Lesson:** phase-2 reviewers should grep for assertions where both operands trace to the same identifier.
- **LLR-014.1's manual UAT (verify `%V` renders as `Wnn` in the Mermaid CDN browser SVG)** is the only TC pytest cannot prove. No e2e/Playwright harness exists. The single-largest assurance gap in the batch.
- **Source-level inspection tests are author-trap-prone.** `test_tc_032_settings_template_is_non_mutating` initially tripped on the author's own Jinja warning comment listing forbidden tokens. Resolved by rewriting the comment, but the underlying lesson is that no review packet flagged it before phase 4 — a trivial pre-commit hook would prevent this class of finding.
- **The pre-existing Pydantic-serializer warning in `tests/test_subtasks.py`** lingered through every phase-3 increment regression run. Inherited from `main`, not in scope, but noisy.

---

## 4 · Root causes of the multi-iteration phases

The 3 iterations in phase 1 and 3 iterations in phase 2 are not separate problems — they're the same root cause expressed at two different gates. Three deeper causes (architect lens):

1. **Phase-1 iteration-1 was authored without code-grounding.** The 5 phase-2 blockers (B-001 LLR-009.1 round-trip incompatible with `import_timeline` parser, B-002 HLR-007 missing data shapes, B-003 actor-empty case overlooked, B-004 path canonicalization missing, B-005 writable-peer guardrails missing) and 14 majors all trace to requirements written from the *intent* of the codebase rather than the *current API surface*. The architect agent did not have `import_timeline`'s signature in front of it when writing LLR-009.1. **Future batches:** phase 1 must include a "code-grounding pass" where every LLR cites the `file:symbol` it constrains.

2. **Iteration-2 fixes were not re-grounded against the same API surface that broke iteration 1.** B-006 and B-Q-001 were *introduced* by the iteration-1 patches because the patches were applied to the requirements doc without re-reading the code. A symbol-level diff (which functions/types are referenced by which LLRs) between iter-1 and iter-2 would have caught these mechanically.

3. **The CR-backlog mechanism was the right call after iteration 2, but should have been available from iteration 1.** Three full iterations plus one inline closure check was 6× the original scope estimate. The conditional-approve-with-deferred-CRs pathway is what unblocked phase 3. **Future batches:** make CR-deferral the *default* gate behaviour at iteration 2 (not iteration 3), with the rule "HIGH security/correctness blocks; everything else becomes a CR with a dated due-phase."

---

## 5 · Metrics

| Metric | Value |
|---|---|
| Phase 1 iterations | 3 |
| Phase 2 iterations | 3 |
| Phase 3 increments | 8 (1, 2, 3, 4, 5, 6a, 6b, 7) |
| Phase 4 iterations | 1 |
| Total user stories | 5 |
| Total HLRs | 14 |
| Total LLRs | 24 |
| Total TCs | 38 |
| Final pytest count | 138 |
| Net new tests this batch | ~68 (38 batch TCs + ~30 sub-cases / parametrized invocations) |
| Pre-existing tests retained | ~70 (8 pre-existing files unchanged) |
| Regressions introduced | 0 |
| CRs raised in phase-2 iter-2 | 26 (2 blockers + 9 majors + 15 minors) |
| CRs closed in phase 3 | 5 (CR-001 HIGH, CR-002 HIGH, CR-003 / -004 / -005 MEDIUM) |
| CRs deferred to phase 5/6 | 5 (CR-006 MEDIUM, CR-007 LOW, CR-008 LOW, CR-009 LOW, CR-010 LOW bundle) |
| Manual UAT pending | 1 (TC-038 Mermaid CDN render) |
| Per-increment full-suite runtime | 8.76–10.14 s (final: 9.49 s) |

### Decisions log highlights

| Phase | Decision | Notes |
|---|---|---|
| P1 iter 1 | approved (5 US, 11 HLR, 15 LLR, 26 TC) | First gate. Locked D-001..D-005. |
| P2 iter 1 | iterate (5 blockers, 14 majors, 15 minors) | Forced phase-1 iter-2. |
| P1 iter 2 | approved (14 HLR, 24 LLR, 38 TC) | Single combined pass closed 5 blockers + 14 majors + 15 minors. |
| P2 iter 2 | iterate (2 NEW blockers, 7 majors) | Iter-1 fixes introduced new defects. |
| P1 iter 3 | approved | Closure pass; method-distribution arithmetic also fixed. |
| P2 iter 3 | **conditional approve with deferred CRs** | User chose to defer 1 HIGH + 9 majors as CR-001..CR-010. |
| P3 ×8 | per-increment approval | All gates approved on first pass. |
| P4 | validation pass with 1 pending UAT | Phase 4 closes; 38/38 TCs PASS. |

---

## 6 · Items proposed for the next batch

Ranked by combined priority (architect + qa lens, deduplicated):

### Highest priority — close remaining HIGH/MEDIUM debt and the manual UAT

1. **Add Playwright smoke tests for HLR-007 / HLR-008 (week chips) and HLR-010 (Settings page).** Closes R-005 / R-007 / G-007 in one batch. **TC-038's manual UAT collapses into an automated visual assertion.** Blocker for confidently shipping any future Mermaid axis or template change.
2. **Close CR-006 (venv / site-packages demotion)** — security follow-up. ~3-minute edit to extend `_demote_dangerous_writable_peers` predicates with `~/.venv`, `~/venv`, `~/.local`, `~/AppData/Local/Programs/Python`. Block-list patch.
3. **Close CR-007 (`actor=unknown` peer-visible carve-out)** — add §6.3 R-012 + a one-time stderr warning at startup when `app.state.user == "unknown"` AND any peer root is configured. Add a regression test verifying the warning fires. ~10–15 minutes total.
4. **Move from block-list to allow-list on writable-peer guardrails (R-011).** Today `_demote_dangerous_writable_peers` denies a hand-curated list of dangerous prefixes; an allow-list would require the operator to opt every writable peer into a path under an explicitly-approved root. Larger refactor — 2-increment batch on its own.

### High priority — architectural / process hardening

5. **Address the `render_timeline` None→today defaulting** (Increment 2 discovery). Replace silent substitution with either an explicit `skip` (don't emit the Gantt row) or a logged warning. Add a regression test pinning the chosen behavior so a future fix is a deliberate breaking change. Architecturally hot — masks data-quality issues from users.
6. **Decompose LLR-012.1's env-var branch.** The predicate should consume parsed-config state, not re-read `os.environ`. Removes the Windows-test footgun (eliminates `_strip_windows_env` from 4 test files) and aligns with the existing pattern where `Settings.load` is the only `os.environ` reader.
7. **Add Mermaid CDN Subresource Integrity (R-008).** The `<script src="…mermaid…">` tag in `base.html` has no `integrity=` / `crossorigin=` attribute. A compromised CDN can inject arbitrary JS into every Gantt-rendering page. One CR-sized increment.
8. **Add a phase-1 "code-grounding pass" to the dev-flow skill itself.** Every LLR must cite `file:symbol` of the constraint target. **Process change** — but the single highest-leverage fix for the iter-1/iter-2 churn documented in §4.

### Medium priority — polish + consistency

9. **Add CSS for `.week-chip`, `.inbox-claimed`, `.settings-peer-row`** in `app/static/styles.css` and `styles.redesign.css`. Increment 1/6b/7 added the markup; the dark `--muted` variable is documented as already lifted to `#c9d6ea` for AA contrast, the chip should consume it.
10. **Document explicitly that `data_root` is `self._writable_roots[0]`** in `StorageService` (CR-010 candidate). One-line module docstring would prevent the next contributor from flipping the order.
11. **Move CR-010's 12 deferred minors into the affected test files.** Highest-value items: split TC-020 into TC-020a (`..`) + TC-020b (symlink); add TC-031 "exists-but-not-a-dir" sub-case; pin TC-034's `capsys` mechanism; add §5.4.A `2027-01-01 (Fri) → W53` Friday-after-NY case.
12. **Strengthen TC-024's negative-context assertion.** Currently uses a 600-char window; should parse the HTML and grep within the specific `<li class="is-peer">` row.
13. **Add a `_strip_windows_env` shared `conftest.py` fixture** so the four current test files don't reimplement the helper. (Subsumed by item 6 if the LLR-012.1 refactor lands.)

### Low priority — telemetry

14. **Run `pytest --durations=10`** on the closing batch to surface any slow tests. Suite has grown ~2× this batch.

---

## 7 · Verdict

Batch closes with **38/38 TCs PASS**, 0 regressions, 5/10 CRs closed (including all HIGH-severity CRs), and a clean phase-4 gate. The headline US-002 (writable peers + guardrails), US-003 (actor + inbox attribution + identity gate + sanitization), US-004 (ISO calendar week), and US-005 (read-only Settings page) are functionally complete and validated. US-001 (configurable data root) was already implemented in PR #18 and continues to work.

**Process retrospective:** the 3+3 iteration count in phases 1–2 is the single biggest cost. The root cause (phase-1 LLRs authored without code-grounding) has a clear and cheap mitigation: add a "code-grounding pass" to the dev-flow skill so every LLR cites `file:symbol`. The CR-deferral pathway is now battle-tested and should become the default at iteration-2 gates.

**Outstanding obligation:** TC-038's manual UAT (5-minute browser check that `%V` renders as `Wnn`) — recommended to either run before phase 6 OR formalize it as the first item of the next batch's Playwright work.

The user decides at the gate: **close batch**, **open new batch** (carrying the proposed-items list above as fresh user stories), or **iterate this phase** (e.g., to run the manual UAT now and update phase-4 evidence).
