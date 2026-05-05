# Increment 004 — Peer-root config schema with `writable` flag

**Batch:** `2026-05-04-batch-01` · **Phase:** 3 · **Increment:** 4 / N · **Date:** 2026-05-04

## 1 · What changed

Three LLRs implemented:

- **LLR-001.1** — `app/settings.py::_resolve_peer_roots` now returns `list[tuple[str, Path, bool]]`. The TOML branch reads the optional `writable` key per entry; the env-var branch (`PROJSTATUS_PEER_ROOTS=label=path,…`) always sets `writable=False` because the env syntax has no place to express it.
- **LLR-001.2** — `Settings.peer_roots` type annotation updated to `list[tuple[str, Path, bool]]`. `app/main.py::create_app` passes the triples through to `app.state.peer_roots` unchanged. `create_app(tmp_path)` continues to set `peer_roots = []`.
- **LLR-002.1** — TOML entries that omit `writable` resolve to `False`. Non-bool values (`"yes"`, `"true"`, `1`, `0`, etc.) coerce to `False` rather than raising — implemented by `entry.get("writable", False) is True`, which only accepts the literal `bool` `True`.

Eleven test cases added in a new file (`tests/test_peer_roots_config.py`):

- **TC-001** (HLR-001) — TOML `writable=true` is preserved as `True`.
- **TC-002** (HLR-002) — TOML omitting `writable` defaults to `False`.
- **TC-015** (LLR-001.1) — triple shape from both TOML and env sources; env always non-writable.
- **TC-016** (LLR-001.2) — `app.state.peer_roots` is `[]` for `create_app(tmp_path)` and well-formed triples (with `bool` writable) for `create_app()` over env config.
- **TC-017** (LLR-002.1) — parametrized over 7 raw `writable` values: only the literal Python `True` becomes `True`; everything else (None, `"yes"`, `1`, `0`, `"true"`, etc.) becomes `False`.

Two existing tests updated to match the new tuple shape (no behavior change, just destructuring):
- `tests/test_settings.py` — three test functions had `for label, _ in settings.peer_roots` patterns; updated to 3-element destructuring. Added two assertions on the writable defaulting (env always-False, TOML omit defaults False).
- `tests/test_peer_inbox.py` — two `read_peer_addendums([(label, path), ...])` calls updated to the 3-tuple shape `(label, path, False)`.

## 2 · Files modified (5 / 5 cap — at the limit)

| Path | Change |
|------|--------|
| [app/settings.py](app/settings.py:40) | `_resolve_peer_roots` return type and body now produce 3-tuples; `Settings.peer_roots` type annotation updated. |
| [app/services/storage.py](app/services/storage.py:733) | `read_peer_addendums` signature updated to `list[tuple[str, Path, bool]]`; iterator destructures `for label, root, _writable in peer_roots:` (writable intentionally ignored per LLR-005.1 — addendums are always read regardless of writable state). Docstring extended. |
| [tests/test_settings.py](tests/test_settings.py) | 3 destructurings updated; 2 new assertions on writable defaulting. |
| [tests/test_peer_inbox.py](tests/test_peer_inbox.py) | 2 `read_peer_addendums` calls updated to pass 3-tuples. |
| [tests/test_peer_roots_config.py](tests/test_peer_roots_config.py) | NEW: 5 test functions (one parametrized over 7 cases → 11 total invocations). |

5 files total — at the cap. The increment intentionally does NOT touch `app/main.py` because the consumers there only pass `app.state.peer_roots` through to `read_peer_addendums` without destructuring.

## 3 · How to test

```
.venv/Scripts/python -m pytest tests/test_peer_roots_config.py tests/test_settings.py tests/test_peer_inbox.py -v
.venv/Scripts/python -m pytest                                          # full suite
```

## 4 · Test results

**Targeted (`tests/test_peer_roots_config.py`):**

```
collected 11 items

tests\test_peer_roots_config.py ...........                              [100%]

============================== 11 passed in 0.68s ==============================
```

**Combined (peer_roots_config + settings + peer_inbox):**

```
collected 20 items

tests\test_peer_roots_config.py ...........                              [ 55%]
tests\test_settings.py .....                                             [ 80%]
tests\test_peer_inbox.py ....                                            [100%]

============================== 20 passed
```

**Full suite (regression check):**

```
94 passed, 1 warning in 7.85s
```

Pre-Increment-4 baseline was 83 tests. +11 → 94. No new warnings; the single existing warning (Pydantic enum serializer in `tests/test_subtasks.py`) is unaffected.

## 5 · Risks

1. **Breaking change to `Settings.peer_roots` and `read_peer_addendums` tuple shape.** The 2-tuple → 3-tuple migration touches 4 existing files (settings.py, storage.py, test_settings.py, test_peer_inbox.py) plus 1 new test file. All consumers are inside the repo and have been migrated. There's no external API surface to worry about.
2. **`writable` coercion is strict (`is True`)** — only the literal Python `True` is accepted; `1`, `"yes"`, `"true"` all become `False`. This is per LLR-002.1's "non-bool value coerces to false rather than raising" — strictness is the safe direction (any ambiguity → no write privilege). Operators with TOML files that intended `writable=true` (lowercase, the TOML literal) will get the bool `True` correctly because `tomllib` parses TOML booleans as Python `bool`.
3. **`app/main.py` not modified.** The consumer there (`app.state.peer_roots = peer_roots` and the two `read_peer_addendums(...)` callers) just passes the value through without destructuring. The type annotation on `app.state` is dynamic so no static check breaks. Verified by the full-suite regression.
4. **No CRs touched or closed by this increment.** CR-005 (Unicode bidi strip) and CR-006 (venv demotion) belong to a future identity-gating / writable-peers-defenses increment.

## 6 · Pending items

The following remain explicitly **NOT covered** by this increment:

- US-002 storage-layer LLRs — LLR-003.1 (reject writes), LLR-003.2 (`writable_roots` arg), LLR-003.3 (path canonicalization).
- US-002 defensive-guardrails LLR — LLR-012.1 (demote `/`, `~`, etc.), HLR-012.
- US-003 LLRs — LLR-004.1, LLR-005.1, LLR-005.2, LLR-005.3, LLR-013.1, LLR-013.2, LLR-013.3.
- US-005 LLRs — LLR-010.1, LLR-010.2, LLR-011.1.
- Open CRs — CR-001 (HIGH), CR-005, CR-006, CR-007, CR-008, CR-009, CR-010.

## 7 · Suggested next task

**Increment 5 — Storage gating + canonicalization + writable-peer guardrails.**

This is the security-heavy increment that closes the writable-peer write surface introduced by Increment 4's flag.

- Scope: LLR-003.1 (reject writes when project_dir not under writable_roots) + LLR-003.2 (`writable_roots: list[Path]` constructor arg) + LLR-003.3 (path canonicalization with `Path.resolve` + `is_relative_to`) + LLR-012.1 (demote dangerous writable paths: `/`, drive root, `Path.home()`, `data_root` ancestor + sensitive home children + Windows `%APPDATA%` etc.).
- TCs: TC-003, TC-012, TC-018, TC-019, TC-020, TC-034.
- Files (estimated 3-4): `app/services/storage.py`, `app/settings.py` (extend with `_demote_dangerous_writable_peers`), `app/main.py` (pass `writable_roots` to `StorageService`), `tests/test_writable_peers.py` (NEW).
- Dependencies: requires LLR-001.1 + LLR-001.2 + LLR-002.1 (this increment) — satisfied.
- CRs touched: CR-006 (venv demotion) closes if LLR-012.1's block list is extended per the CR.
- Estimated effort: ~40–50 minutes — more involved than prior increments.

After Increment 5: Increment 6 = identity gating (LLR-013.1) + sanitization (LLR-013.2 / LLR-013.3) — closes CR-001 / CR-005.

---

**Stop.** Increment 4 is complete. No Increment 5 work has begun. Awaiting user approval before proceeding.
