# Increment 006b — US-003 inbox + actor display

**Batch:** `2026-05-04-batch-01` · **Phase:** 3 · **Increment:** 6b / N · **Date:** 2026-05-05

## 1 · What changed

Four LLRs covered (two with code edits, two with verification-only TCs since the existing infrastructure already met the spec).

**LLRs implemented (code edits):**

- **LLR-005.2** — `read_peer_addendums` in `app/services/storage.py` now constructs the throwaway peer `StorageService` with `writable_roots=[]`. Defense-in-depth: any future caller that accidentally wires a peer-read service into a write path will fail closed with `PeerWriteForbidden` rather than corrupting the peer's data root.
- **LLR-005.3** — `app/templates/inbox.html` peer-row markup now renders `<span class="inbox-actor">{{ actor }} <em class="inbox-claimed">(claimed)</em></span>` alongside the existing `peer · <label>` chip. The `(claimed)` qualifier is greppable so phase-4 tests can assert it explicitly. Own-app rows render the actor without the qualifier.

**LLRs verified (no code change needed — existing infrastructure already conforms):**

- **LLR-004.1** — `save_project` already passes `actor` through to the addendum and CHANGELOG.md unchanged. Verified by TC-021 against a writable-peer write path: the addendum's `actor` and the CHANGELOG line both contain the local user, not the peer's owner. Mounted on Increment 5's `_check_writable` + Increment 6a's `_check_actor_for_peer_write` gates so the actor that lands on disk is the same one the local route passed in.
- **LLR-005.1** — `read_peer_addendums` was already iterating peer roots regardless of writable state (the writable flag is consumed solely by the storage gate, not the read path). TC-022 explicitly verifies that triples with `writable=True` and `writable=False` both contribute identically.

**TCs added (5):**

- **TC-005** (HLR-005 behavioural) — A writable-peer addendum written by local-user `bob` surfaces in another instance's `/inbox` (configured with `bob`'s data root as a peer named `shared`). The viewer sees the row tagged `peer · shared` with `bob` as the actor and the `(claimed)` qualifier.
- **TC-021** (LLR-004.1) — Cross-storage save to a writable peer records `actor=bob` (not `actor=alice` who originally seeded the peer); CHANGELOG.md confirms.
- **TC-022** (LLR-005.1) — `read_peer_addendums` returns the same triple shape for `(writable=True)` and `(writable=False)` peers; both labels and actors appear in the merged stream.
- **TC-023** (LLR-005.2) — Patches `StorageService.__init__` to capture all `writable_roots` arguments during a `read_peer_addendums` call; asserts `[]` was passed at least once.
- **TC-024** (LLR-005.3) — `/inbox` HTML for a peer row contains both `peer · alice` and `(claimed)`. The own-app row's local context substring does NOT contain `(claimed)`.

## 2 · Files modified (3 / 5 cap)

| Path | Change |
|------|--------|
| [app/services/storage.py](app/services/storage.py) | One-line: `peer_storage = StorageService(peer_config, writable_roots=[])` (was `StorageService(peer_config)`). 4-line comment block documenting LLR-005.2 rationale. |
| [app/templates/inbox.html](app/templates/inbox.html) | Peer row now wraps the actor in `<span class="inbox-actor">{{ addendum.actor }} <em class="inbox-claimed">(claimed)</em></span>`. 4-line `{# ... #}` comment block documenting LLR-005.3 rationale. Own-row markup unchanged. |
| [tests/test_inbox_attribution.py](tests/test_inbox_attribution.py) | NEW: 5 tests covering TC-005, TC-021, TC-022, TC-023, TC-024. |

3 files total — under the 5-file cap.

## 3 · How to test

```
.venv/Scripts/python -m pytest tests/test_inbox_attribution.py -v
.venv/Scripts/python -m pytest                                          # full suite
```

## 4 · Test results

**Targeted (`tests/test_inbox_attribution.py`):**

```
collected 5 items

tests\test_inbox_attribution.py .....                                    [100%]

============================== 5 passed in 1.02s ==============================
```

**Full suite (regression check):**

```
128 passed, 1 warning in 9.12s
```

Pre-Increment-6b baseline was 123 tests. +5 → 128. No new warnings; the single existing warning (Pydantic enum serializer in `tests/test_subtasks.py`) is unaffected.

## 5 · Risks

1. **Peer addendums unaffected by the throwaway hardening at the read path.** `list_recent_addendums` is a read-only operation that never calls `save_project` on the throwaway, so no behavior change. The hardening defends against future regressions only.
2. **`(claimed)` qualifier is text-only — no CSS yet.** The `<em class="inbox-claimed">` is rendered as italic by the browser default. A small CSS rule (e.g., `font-size: 0.85em; color: var(--muted);`) would be a polish follow-up. Not mandated by any LLR.
3. **TC-024 negative-context assertion is fragile.** It checks "`(claimed)` does not appear in a 600-char window after the own-slug substring." If a future template change moves the peer row to immediately follow the own row in DOM order, the window could overlap and false-fail. A stronger assertion would parse the HTML to extract the specific `<li class="is-peer">` row, but the current substring approach is sufficient for the present template structure and matches the existing test pattern in `test_peer_inbox.py`.
4. **No CRs touched or closed by this increment.** US-003 is now functionally complete; CR-007 (the peer-visible `actor=unknown` carve-out documentation) is the only US-003-related CR remaining and is a doc-only LOW.

## 6 · CR backlog status

Unchanged — 5/10 closed, 5 remaining (0 HIGH, 1 MEDIUM CR-006, 4 LOW CR-007/-008/-009/-010).

## 7 · Pending items

- **US-005 LLRs** — LLR-010.1 (Settings page route), LLR-010.2 (Settings template), LLR-011.1 (no mutating routes).
- **Open CRs** — CR-006, CR-007, CR-008, CR-009, CR-010.

## 8 · Suggested next task

**Increment 7 — US-005 Settings page (final user-story increment).**

- Scope: LLR-010.1 (`GET /settings` route rendering `data_root`, peer rows with RW/RO + reachable, user) + LLR-010.2 (`app/templates/settings.html` with no `<form>`/`<input>`/`<button type=submit>`/`method=post`) + LLR-011.1 (no `POST`/`PUT`/`PATCH`/`DELETE` handlers on `/settings`).
- Files (estimated 4): `app/main.py` (new GET route), `app/templates/settings.html` (NEW), `app/templates/base.html` (or `_sidebar.html` — add a Settings nav link via `build_sidebar_context`), `tests/test_settings_page.py` (NEW).
- TCs: TC-010 (HLR-010 behavioural), TC-011 (HLR-011 behavioural — POST/PUT/PATCH/DELETE all return 405), TC-031 (LLR-010.1), TC-032 (LLR-010.2 inspection), TC-033 (LLR-011.1).
- CRs touched: none directly; CR-009 (`.gitignore` recommendation) lives in USER_GUIDE.md, not the Settings page.
- Estimated effort: ~30–40 minutes.

After Increment 7: **all 24 LLRs complete**. Phase 3 closes; Phase 4 begins (validation execution against §5.2 — 38 TCs).

---

**Stop.** Increment 6b is complete. No Increment 7 work has begun. Awaiting user approval before proceeding.
