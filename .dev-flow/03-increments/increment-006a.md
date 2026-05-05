# Increment 006a — Identity gate + input sanitization (closes CR-001, CR-005)

**Batch:** `2026-05-04-batch-01` · **Phase:** 3 · **Increment:** 6a / N · **Date:** 2026-05-05

## 1 · What changed

Three LLRs implemented + two CRs closed (one HIGH security, one MEDIUM security).

**LLRs implemented:**

- **LLR-013.2** — `_resolve_user` in `app/settings.py` now applies a per-source sanitization pipeline via `_sanitize_user_candidate`:
  - Strips control characters (`\x00`–`\x1f`, `\x7f`).
  - Strips Unicode bidi / RTL overrides (U+202A–U+202E, U+2066–U+2069).
  - Strips zero-width / NBSP / NEL: U+200B, U+200C, U+200D, U+FEFF, U+0085, U+00A0 (CR-005 closure).
  - Rejects (returns `None`, falls through to next source) any input originally containing `\r` or `\n`.
  - Caps at 64 characters.
  - **Never synthesizes `"unknown"`** from a non-fall-through source — the literal `"unknown"` only arrives via the final fall-through after `os.getlogin()` fails, where the LLR-013.1 gate catches it.

- **LLR-013.3** — `_append_changelog` in `app/services/storage.py` now runs both `headline` and `note` through `_sanitize_changelog_field`. The pipeline order is the load-bearing CR-001 fix:
  1. Newline replace (`\r`, `\n` → single space).
  2. **`&` → `&amp;`** pre-escape.
  3. Escape `[`, `]`, `|`, `<`, `>` to entities.
  4. Cap at 200 characters post-escape.
  Without the `&` pre-escape, an attacker-controlled note containing the literal `&#91;click&#93;(javascript:alert)` would survive untouched and reconstruct as a clickable markdown link in any HTML-rendering Markdown viewer (OneDrive web preview, GitHub).

- **LLR-013.1** — `StorageService._check_actor_for_peer_write` runs in `save_project` AFTER `_check_writable` (per N-S-001 gate ordering). When `actor` is empty, `None`, or `"unknown"` AND the resolved `project_dir` is NOT under `data_root` (the first entry of `writable_roots`), the call raises `PeerWriteForbidden` with a message containing `actor` and the resolved path. Writes to `data_root` with `actor="unknown"` continue to succeed (A-010 — own-projects work on unconfigured single-user machines).

**CRs closed:**

- **CR-001 (HIGH security)** — `&` pre-escape implemented and verified by `test_tc_037_pre_escape_blocks_entity_bypass`. Entity-bypass injection through writable peers' CHANGELOG.md is now blocked.
- **CR-005 (MEDIUM security)** — Unicode bidi + zero-width strip implemented and verified by parametrized fixtures in `test_tc_036_zero_width_and_special_whitespace_stripped` plus the dedicated `test_tc_036_unicode_rlo_is_stripped`.

**TCs added (22):**

- **TC-013** (HLR-013) — writable peer + `actor="unknown"` raises; `data_root` + `actor="unknown"` succeeds with addendum.actor=="unknown".
- **TC-035a/b/c** (LLR-013.1) — three sub-cases including the gate-ordering proof: non-writable peer + unknown actor produces a writability error (NOT actor error).
- **TC-036 (×7)** (LLR-013.2) — env-with-newline falls through to config; 200-char cap; `\x00` stripped; U+202E RLO stripped; parametrized over 5 zero-width / NEL / NBSP fixtures; sanitizer never returns `"unknown"`.
- **TC-037 (×8)** (LLR-013.3) — markdown-link brackets escaped; HTML tags escaped; CR-001 entity-bypass round-trip (input `&#91;` → on disk `&amp;#91;`); newlines collapse to spaces; pipes escaped; post-escape cap at 200; thousand-newline regression; on-disk integration check.

## 2 · Files modified (4 / 5 cap)

| Path | Change |
|------|--------|
| [app/settings.py](app/settings.py) | New `_USER_STRIP_CHARS` + `_USER_STRIP_TRANS` (built once at module load). New `_USER_MAX_LEN = 64`. New `_sanitize_user_candidate(raw) -> str | None` (per-source sanitizer). `_resolve_user` rewritten to chain three sanitized sources (env → config.toml → `os.getlogin()`) with `"unknown"` only at the final fall-through. |
| [app/services/storage.py](app/services/storage.py) | New `_CHANGELOG_FIELD_MAX_LEN = 200`. New `_sanitize_changelog_field(raw)` with the 4-step pipeline. `_append_changelog` calls the sanitizer for headline + note. New `StorageService._check_actor_for_peer_write(project_dir, actor)`. `save_project` invokes the actor check immediately after `_check_writable`. |
| [tests/test_identity_gate.py](tests/test_identity_gate.py) | NEW: 4 tests (TC-013, TC-035a, TC-035b, TC-035c) covering the writable-peer/unknown-actor matrix and the gate-ordering invariant. |
| [tests/test_input_sanitization.py](tests/test_input_sanitization.py) | NEW: 18 tests covering TC-036 (LLR-013.2) and TC-037 (LLR-013.3). |

4 files total — under the 5-file cap.

## 3 · How to test

```
.venv/Scripts/python -m pytest tests/test_identity_gate.py tests/test_input_sanitization.py -v
.venv/Scripts/python -m pytest                                          # full suite
```

## 4 · Test results

**Targeted (`tests/test_identity_gate.py`):** 4 passed.
**Targeted (`tests/test_input_sanitization.py`):** 18 passed.

**Full suite (regression check):**

```
123 passed, 1 warning in 8.76s
```

Pre-Increment-6a baseline was 101 tests. +22 → 123. No new warnings; the single existing warning (Pydantic enum serializer in `tests/test_subtasks.py`) is unaffected.

## 5 · Risks

1. **`_resolve_user` chain depends on `os.getlogin()` raising or returning empty when `OSError` is raised.** Pre-existing behavior; my refactor preserves the try/except. Verified by full-suite regression (existing settings tests unchanged in expected output).
2. **Sanitizer string literals on Windows console.** The `_USER_STRIP_CHARS` constant contains literal Unicode bidi / zero-width characters. The Python source file is UTF-8 (per the existing repo convention) and `tomllib` parses TOML in UTF-8; no encoding regression.
3. **`_check_actor_for_peer_write` reads `self._writable_roots[0]` as `data_root`.** This relies on `app/main.py` passing `[data_root, *writable_peer_paths]` in that order (Increment 5). Documented as an invariant in the docstring; if a future caller passes them in a different order, the gate would mis-classify. Consider an explicit `data_root` attribute on `StorageService` in a future polish increment (CR-010 candidate).
4. **No template change for LLR-005.3 (peer-supplied actor display).** Increment 6b (next) will close that.

## 6 · CR backlog status

**Closed: 5 / 10** (CR-001, CR-002, CR-003, CR-004, CR-005).
**Remaining: 5** (0 HIGH, 1 MEDIUM CR-006, 4 LOW CR-007/-008/-009/-010).

The headline HIGH-severity security blocker (CR-001 entity-bypass injection) is now closed by code AND verified by the dedicated TC-037 round-trip test.

## 7 · Pending items

- **LLR-004.1** — actor passing through `save_project` for writable-peer writes (already partly true: every existing route passes `actor=current_actor(request)`; LLR-004.1 just requires explicit verification).
- **LLR-005.1** — `read_peer_addendums` iterates writable peers identically to read-only (already true post-Increment 4; needs explicit TC-022).
- **LLR-005.2** — throwaway `StorageService` for peer reads passes `writable_roots=[]`.
- **LLR-005.3** — peer-supplied actor display as `peer · <label>: <actor (claimed)>`.
- **LLR-010.1, LLR-010.2, LLR-011.1** — Settings page route + template + no mutating routes (US-005).
- **Open CRs** — CR-006 (venv demotion list), CR-007 (`actor=unknown` peer-visible carve-out doc), CR-008 (TC-035 compound semantics — covered for now by separate `test_tc_035a/b/c` test functions; explicit §5.3 line still open), CR-009 (`.gitignore` USER_GUIDE.md callout), CR-010 (12 deferred minors bundle).

## 8 · Suggested next task

**Increment 6b — US-003 inbox + actor display (no remaining HIGH-priority CRs).**

- Scope: LLR-004.1 (actor passing — verification + TC-021) + LLR-005.1 (`read_peer_addendums` writable iteration — TC-022) + LLR-005.2 (throwaway non-writable — TC-023) + LLR-005.3 (`peer · <label>: <actor (claimed)>` template — TC-024).
- Files (estimated 3): `app/services/storage.py` (one-line `writable_roots=[]` for the throwaway), `app/templates/inbox.html` (qualifier), `tests/test_inbox_attribution.py` (NEW, covers TC-005, TC-021..TC-024).
- TCs: TC-005, TC-021, TC-022, TC-023, TC-024.
- CRs touched: none directly.
- Estimated effort: ~25 minutes.

After Increment 6b: **Increment 7 — US-005 Settings page** (LLR-010.1, LLR-010.2, LLR-011.1) — the last user-story increment, then phase-3 will be ready to close.

---

**Stop.** Increment 6a is complete. No Increment 6b work has begun. Awaiting user approval before proceeding.
