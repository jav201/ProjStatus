# Change Requests Backlog — ProjStatus — Batch 2026-05-04-batch-01

> Generated 2026-05-04 from phase-2 iteration-3 review findings the user explicitly chose to DEFER rather than block phase 3 on.
> All entries here are accepted technical debt against the iteration-3 requirements doc. They MUST be addressed before this batch closes (phase 5 sign-off) OR explicitly carried to a follow-up batch.

## Severity legend
- **HIGH** — security vulnerability or correctness defect that invalidates a TC. Must address before phase 5 OR explicitly carry to a named follow-up batch with rationale.
- **MEDIUM** — testability or design gap that will block phase 4 or weaken validation. Must address before phase 4.
- **LOW** — documentation, polish, or accepted residual risk. May roll to a follow-up batch.

---

## CR-001 (HIGH — security) · LLR-013.3 missing `&` pre-escape — **CLOSED 2026-05-05 (Increment 6a)**

- **Source:** phase-2 iter-3, security finding F1.
- **Risk:** entity-bypass injection in peer CHANGELOG.md. A `note` containing the literal text `&#91;click&#93;(javascript:alert(1))` survives LLR-013.3's escape pass (no `[` or `]` to match). HTML-rendering Markdown viewers (OneDrive web preview, GitHub-rendered CHANGELOG.md) will reconstruct the clickable link, defeating the protection.
- **Fix applied:** `_sanitize_changelog_field` in `app/services/storage.py` runs in this exact order:
  1. Newline replace (`\r`, `\n` → space).
  2. **`&` → `&amp;`** (the new pre-escape — the load-bearing CR-001 fix).
  3. Bracket / pipe / angle escapes (`[`, `]`, `|`, `<`, `>` → numeric/named entities).
  4. Cap at 200 chars POST-escape.
  Verified by `tests/test_input_sanitization.py::test_tc_037_pre_escape_blocks_entity_bypass` — input `&#91;click&#93;` becomes `&amp;#91;click&amp;#93;` on disk; the bare `&#91;` sequence does NOT survive.
- **Closure:** Increment 6a.

## CR-002 (HIGH — correctness) · LLR-009.2 tautological round-trip — **CLOSED 2026-05-04 (Increment 3)**

- **Source:** phase-2 iter-3, architect finding A-1.
- **Risk:** `app/services/mermaid.py::import_timeline` mutates the input `Project` in place and returns the same object. The current LLR-009.2 acceptance `imported, _w, _u, ok = import_timeline(p, render_timeline(p)); assert render_timeline(imported) == render_timeline(p)` is a tautology — `imported is p`, so the equality holds even if `import_timeline` did nothing useful. The test cannot detect a real round-trip regression.
- **Fix applied:** LLR-009.2 + TC-030 acceptance updated to use `deepcopy`:
  ```python
  rendered = render_timeline(p)
  imported, _imported_msgs, _errors, ok = import_timeline(deepcopy(p), rendered)
  assert ok is True
  assert render_timeline(imported) == rendered
  ```
  Verified by `tests/test_mermaid_labels.py::test_tc_030_roundtrip_byte_identical_via_deepcopy` (passing).
- **Closure:** Increment 3 (this batch).

## CR-003 (MEDIUM — testability) · `%V` conditional assertion machine-readable signal source — **CLOSED 2026-05-04 (Increment 3)**

- **Source:** phase-2 iter-3, architect A-3 + qa Q-1.
- **Risk:** TC-014 / TC-038 cannot read the markdown increment review packet at runtime. The conditional `%V`-absence assertion either silently never fires or is implemented inconsistently across runs.
- **Fix applied:** module-level constant added in `app/services/mermaid.py`:
  ```python
  ISO_WEEK_AXIS_TOKEN: Final[str] = "%V"
  ```
  Used by `render_timeline` (axisFormat line) and imported by `tests/test_mermaid_labels.py::test_tc_014_axis_has_w_and_roundtrip_ok` and `::test_tc_038_fallback_token_assertion_is_conditional`. The conditional assertion now reads: `if ISO_WEEK_AXIS_TOKEN != "%V": assert "%V" not in axis_line`. LLR-014.1 + TC-014 + TC-038 acceptance updated in §4 / §5.2.
- **Closure:** Increment 3.

## CR-004 (MEDIUM — correctness/docs) · LLR-009.2 returned-list naming — **CLOSED 2026-05-04 (Increment 3)**

- **Source:** phase-2 iter-3, architect A-2.
- **Risk:** LLR-009.2 names the returned tuple's lists `_warnings` / `_unsupported`. Actual code returns `(project, imported_msgs, errors, supported)` — the second list is success messages (`"Updated milestone..."`, `"Updated task..."`), the third is unsupported-line errors. A future positive assertion on those lists (e.g., `assert len(_warnings) == 0`) would silently invert.
- **Fix applied:** LLR-009.2 acceptance + TC-030 row + TC-014 row + TC-038 row in 01-requirements.md renamed to `_imported_msgs, _errors`. Tests in `tests/test_mermaid_labels.py` use the corrected names.
- **Closure:** Increment 3.

## CR-005 (MEDIUM — security) · LLR-013.2 zero-width Unicode strip — **CLOSED 2026-05-05 (Increment 6a)**

- **Source:** phase-2 iter-3, security F2.
- **Risk:** zero-width characters (U+200B ZWSP, U+200C, U+200D, U+FEFF BOM, U+0085 NEL, U+00A0 NBSP) are not stripped. A malicious peer can write `actor = "alice<U+200B>bob"` which renders as `alicebob` in viewers but `==` compares unequal, defeating the `(claimed)` qualifier greppability and enabling visual impersonation.
- **Fix applied:** `_USER_STRIP_CHARS` in `app/settings.py` now strips control characters (U+0000–U+001F + U+007F), bidi/RTL overrides (U+202A–U+202E, U+2066–U+2069), AND zero-width / NBSP / NEL: U+200B, U+200C, U+200D, U+FEFF, U+0085, U+00A0. Verified by `tests/test_input_sanitization.py::test_tc_036_unicode_rlo_is_stripped` and `::test_tc_036_zero_width_and_special_whitespace_stripped` (parametrized over 5 fixtures).
- **Closure:** Increment 6a.

## CR-006 (MEDIUM — security) · LLR-012.1 venv / site-packages demotion

- **Source:** phase-2 iter-3, security F3.
- **Risk:** RCE on next launch if a malicious peer writes into `~/.venv/projstatus/lib/site-packages/app/__init__.py`. The current LLR-012.1 demotion list catches `~/.config` etc. but not Python virtualenv directories. Operators commonly keep venvs under home.
- **Fix:** extend LLR-012.1 dangerous-path predicates with `~/.venv`, `~/venv`, `~/.local`, `~/AppData/Local/Programs/Python` (Windows). The R-011 allow-list approach is the long-term answer; this CR is the block-list patch.
- **Effort:** ~3 minutes edit.
- **Carry:** address before phase 5.

## CR-007 (LOW — UX/docs) · `actor="unknown"` peer-visible carve-out

- **Source:** phase-2 iter-3, architect A-4.
- **Risk:** US-003 contract degraded for unconfigured single-user machines — peers see `actor="unknown"` in our addendums.
- **Fix (minimum viable):** add §6.3 R-012: "Single-user machines without `PROJSTATUS_USER` set will appear as `unknown` in peers' inboxes — locked carve-out per A-010, but operators with peers configured should set `PROJSTATUS_USER` to avoid noisy attribution." Optionally: emit one-time stderr warning at startup when `app.state.user == "unknown"` AND any peer root is configured.
- **Effort:** ~5 minutes for the risk row; ~10 minutes if also adding the stderr warning HLR/LLR.
- **Carry:** address before phase 5.

## CR-008 (LOW — testability) · TC-035 compound-TC pass semantics

- **Source:** phase-2 iter-3, qa Q-2.
- **Risk:** TC-035 has 3 sub-cases (a/b/c). §5.3 batch acceptance is silent on whether one TC with three sub-cases passes only when all three sub-assertions pass. Validation reporting becomes ambiguous.
- **Fix (pick one):**
  1. Split into TC-035a / TC-035b / TC-035c — each gets its own row in §5.2 and the validation log. Total TC count becomes 40.
  2. Add a §5.3 line: "Compound TCs (those with sub-cases labeled (a), (b), …) pass only if ALL sub-cases pass; a single sub-case failure marks the parent TC failed."
- **Effort:** ~5 minutes either approach.
- **Carry:** address before phase 4.

## CR-009 (LOW — docs) · `.gitignore` guidance for `config.toml`

- **Source:** phase-2 iter-3, security F4.
- **Risk:** operators who keep dotfiles in git may inadvertently commit `~/.config/projstatus/config.toml`, exposing peer paths and disclosure of collaborator filesystem layout.
- **Fix:** USER_GUIDE.md callout — "If you keep your `~/.config` in a git-tracked dotfiles repo, add `projstatus/config.toml` to `.gitignore` BEFORE adding any peer-root entries."
- **Effort:** ~2 minutes edit (in phase 6 documentation phase).
- **Carry:** address in phase 6 (documentation phase).

## CR-010 (LOW — quality) bundle · 12 deferred minors

- **Sources:** phase-2 iter-3 minors A-5, A-6, A-7, A-9 (architect); Q-3, Q-4, Q-5, Q-6, Q-7 (qa); F-7, F-8, F-9 (security). [A-8, F-5, F-6 dropped — informational only, no action needed.]
- **Items:**
  - **A-5** — LLR-012.1 environment-variable predicates may false-positive on WSL/Cygwin where Windows env vars are inherited. Add a one-line note acknowledging "intended behaviour."
  - **A-6** — LLR-013.3 escape set ignores `\t` (tab). Add `\t` → ` ` to step 1's replacement set.
  - **A-7** — TC-035 sub-cases vs §5.2 method-distribution count. Add parenthetical to method-distribution recount: "TC IDs counted, not assertion sub-cases — TC-035 has three sub-assertions in one test." (Folds into CR-008 if option 1 is chosen.)
  - **A-9** — G-009 in traceability matrix §3 vs R-007 in §6.3 track the same gap with different verdicts. Reclass G-009 as `mitigated` OR drop R-007.
  - **Q-3** — TC-020 partial-skip ambiguity. The `..`-segment half doesn't need symlink privilege. Restructure as TC-020a (`..`) + TC-020b (symlink, skippable on Windows-without-Developer-Mode).
  - **Q-4** — TC-031 missing "exists-but-not-a-dir" sub-case. Add: "a peer whose `path` resolves to an existing regular file renders `unreachable`."
  - **Q-5** — TC-034 stderr capture mechanism not pinned. Add: "Test uses `capsys` and asserts `capsys.readouterr().err.count('demoted to read-only') == 1` after triggering load twice in the same process."
  - **Q-6** — §5.4.A missing Friday-after-NY case. Add `2027-01-01 | Fri | W53 | calendar New Year that falls in PREVIOUS ISO year (Friday rule)`.
  - **Q-7** — TC-027 method classification (LLR-007.2 Jinja global) is ambiguous between unit and integration. Pin: "TC-027 is integration: spins a `TestClient` against a route whose template invokes `{{ iso_week_label(...) }}` without route-context injection."
  - **F-7** — Post-escape 200-char cap can truncate mid-entity (`…&#9` instead of `…&#91;`). Garbled but not exploitable. Note as known UX issue in TC-037 acceptance.
  - **F-8** — Settings page Mermaid CDN exposure. Confirm in phase-3 review packet that `settings.html` does NOT extend `base.html` if it doesn't need Mermaid (or at least doesn't load the CDN script).
  - **F-9** — R-011 block-list residual. Documented; no action this batch.
- **Carry:** address in phase 6 (documentation phase) OR roll to a follow-up "polish" batch if time-pressed.

---

## Tracking

- `state.json::decisions_log` records the user decision to defer (entry "conditional-approve-with-deferred-CRs" appended).
- These CRs MUST be revisited at phase-5 retrospective. CRs marked HIGH or MEDIUM cannot be closed by a "no action" decision — they require either a fix in this batch or an explicit carry-forward to a named follow-up batch.
- Acknowledged residuals (no action needed): A-8 (`should` discipline confirmed clean), F-5 (`Path.resolve()` Windows junctions confirmed safe), F-6 (TC-035(b) addendum-actor-unknown locked by A-010).

## Summary table

| CR | Severity | Phase due | Source finding | Effort | Status |
|----|----------|-----------|----------------|--------|--------|
| CR-001 | HIGH | phase 5 | F1 (security) | ~20 min | **closed (Increment 6a)** |
| CR-002 | HIGH | phase 4 | A-1 (architect) | ~10 min | **closed (Increment 3)** |
| CR-003 | MEDIUM | phase 4 | A-3 + Q-1 | ~15 min | **closed (Increment 3)** |
| CR-004 | MEDIUM | phase 4 | A-2 | ~3 min | **closed (Increment 3)** |
| CR-005 | MEDIUM | phase 5 | F2 | ~3 min | **closed (Increment 6a)** |
| CR-006 | MEDIUM | phase 5 | F3 | ~3 min | open |
| CR-007 | LOW | phase 5 | A-4 | ~5–10 min | open |
| CR-008 | LOW | phase 4 | Q-2 | ~5 min | open |
| CR-009 | LOW | phase 6 | F4 | ~2 min | open |
| CR-010 | LOW | phase 6 / follow-up | 12 minors bundled | ~30 min total | open |

**Closed: 5 / 10 (CR-002 + CR-003 + CR-004 — Increment 3; CR-001 + CR-005 — Increment 6a).**
**Remaining backlog: 5 CRs (0 HIGH, 1 MEDIUM, 4 LOW) ≈ ~45 minutes of edit work.**
