# Increment 005 — Storage gating + canonicalization + writable-peer guardrails

**Batch:** `2026-05-04-batch-01` · **Phase:** 3 · **Increment:** 5 / N · **Date:** 2026-05-05

## 1 · What changed

Four LLRs implemented (security-heavy: closes the writable-peer write surface introduced by Increment 4):

- **LLR-003.2** — `StorageService.__init__` accepts a new `writable_roots: list[Path] | None` keyword. When omitted, defaults to `[config.projects_dir.parent]` (the data root). Roots are canonicalized via `Path.resolve(strict=False)` once at construction and stored in `self._writable_roots`.
- **LLR-003.1** — `save_project` calls `self._check_writable(project_dir)` BEFORE any `_write_text` call. If the resolved `project_dir` is not relative to any resolved entry of `self._writable_roots`, a domain-specific `PeerWriteForbidden` (subclass of `PermissionError`) is raised carrying an optional `peer_label` attribute and a descriptive message. No file on disk is touched on rejection.
- **LLR-003.3** — Path canonicalization. `_check_writable` resolves both `project_dir` and every writable-root with `Path.resolve(strict=False)` and uses `Path.is_relative_to(resolved_root)` for the containment check. This is symlink-safe (Windows junctions and POSIX symlinks both follow `Path.resolve`'s `realpath` semantics) and `..`-segment-safe (resolution normalizes the path components even when intermediates don't exist).
- **LLR-012.1** — `Settings.load` now runs a post-pass `_demote_dangerous_writable_peers` after `_resolve_peer_roots` returns and after `_resolve_data_root` is computed (because the ancestor-of-data-root predicate needs `data_root`). The post-pass iterates writable triples; for any whose resolved path matches a dangerous-path predicate (`filesystem-root`, `home-dir`, `data-root-ancestor`, `ssh-credentials`, `aws-credentials`, `config-dir`, `gnupg-credentials`, `kube-config`, `docker-config`, POSIX `system-bin:/etc|/usr|/var|/bin|/sbin`, Windows `windows-appdata|localappdata|programdata`), it sets `writable=False` and emits one stderr warning per `(label, resolved-path)` per process lifetime via the `_DEMOTED_WARNED: set[str]` tracker. The warning message includes the matched predicate name so phase-4 inspection can grep it.

Seven test cases added in a new file (`tests/test_writable_peers.py`):

- **TC-003** (HLR-003 behavioural) — cross-storage save against a non-writable peer raises `PeerWriteForbidden`; `project.json` SHA-256 unchanged before/after.
- **TC-018** (LLR-003.1) — write outside `writable_roots` raises `PermissionError`; an "inside" project's bytes are unchanged (negative control).
- **TC-019** (LLR-003.2) — explicit kwarg accepted; default `writable_roots` is `[projects_dir.parent]` when omitted.
- **TC-020a** (LLR-003.3) — `..`-segment escape rejected (always runs).
- **TC-020b** (LLR-003.3) — symlink escape rejected (skipped on Windows-without-Developer-Mode via `pytest.skip`).
- **TC-012** (HLR-012 behavioural) — TOML `path="<filesystem-root>" writable=true` is demoted to `writable=False`; one stderr warning emitted including `filesystem-root` predicate name.
- **TC-034** (LLR-012.1) — every dangerous-path branch (`filesystem-root`, `home-dir`, `data-root-ancestor`, `ssh-credentials`) demotes; safe peer remains writable; warnings emitted exactly once per process (re-running the same triples produces zero new warnings).

One existing test patched:
- `tests/test_peer_roots_config.py::test_tc_001_writable_true_preserved_from_toml` — added `monkeypatch.delenv` for Windows `APPDATA`/`LOCALAPPDATA`/`PROGRAMDATA` so pytest's `tmp_path` (which on Windows lives under `%LOCALAPPDATA%\Temp`) is not incidentally seen as a dangerous writable subtree by LLR-012.1's predicate. Test isolation pattern documented in the test_writable_peers.py helper `_strip_windows_env`.

## 2 · Files modified (5 / 5 cap — at the limit)

| Path | Change |
|------|--------|
| [app/services/storage.py](app/services/storage.py:40) | New exception `PeerWriteForbidden(PermissionError)` with `peer_label` attribute. `StorageService.__init__` gained `writable_roots` kwarg + `self._writable_roots` resolved list. New `_check_writable(project_dir)` private method. `save_project` calls `_check_writable` before any `_write_text`. |
| [app/settings.py](app/settings.py) | New module-level `_DEMOTED_WARNED: set[str] = set()`. New `_dangerous_writable_predicate(resolved_path, data_root) -> str | None`. New `_demote_dangerous_writable_peers(peer_roots, data_root) -> list[triple]`. `Settings.load` calls the post-pass after resolving `data_root` and before constructing the `Settings` instance. |
| [app/main.py](app/main.py) | `create_app` builds `writable_peer_paths = [path for ... if writable]` and passes `writable_roots=[data_root, *writable_peer_paths]` to `StorageService(config, ...)`. |
| [tests/test_peer_roots_config.py](tests/test_peer_roots_config.py) | TC-001: 3-line `monkeypatch.delenv` block for Windows env vars. |
| [tests/test_writable_peers.py](tests/test_writable_peers.py) | NEW: 7 test functions (TC-003, TC-012, TC-018, TC-019, TC-020a, TC-020b, TC-034). |

5 files total — at the cap, but all changes are tightly scoped to the four LLRs in scope.

## 3 · How to test

```
.venv/Scripts/python -m pytest tests/test_writable_peers.py tests/test_peer_roots_config.py -v
.venv/Scripts/python -m pytest                                          # full suite
```

## 4 · Test results

**Targeted (`tests/test_writable_peers.py`):**

```
collected 7 items

tests\test_writable_peers.py .......                                     [100%]

============================== 7 passed in 0.36s ==============================
```

**Combined (writable_peers + peer_roots_config):**

```
collected 18 items
tests\test_writable_peers.py .......                                     [ 38%]
tests\test_peer_roots_config.py ...........                              [100%]
============================== 18 passed
```

**Full suite (regression check):**

```
101 passed, 1 warning in 8.48s
```

Pre-Increment-5 baseline was 94 tests. +7 → 101. No new warnings; the single existing warning (Pydantic enum serializer in `tests/test_subtasks.py`) is unaffected.

## 5 · Risks

1. **Pre-existing Mermaid-roundtrip None→today defaulting still latent.** Increment 2 flagged that `render_timeline` defaults `task.start_date=None` to today. With my new gate, `save_project` is now guarded by writable_roots — but the round-trip behavior is unchanged. No interaction.

2. **`_check_writable` runs on `restore_history` too** (which calls `save_project`). Verified by the regression suite — `tests/test_routes.py` and others that exercise `restore_history`-adjacent code all pass. `restore_history` saves into the same project_dir under data_root, so no impact.

3. **`writable_roots=[]` is now a meaningful state** — every save raises. The throwaway `StorageService` instances inside `read_peer_addendums` (LLR-005.2 future increment) should pass `writable_roots=[]` to defend against accidental writes through peer-only services. NOT done in this increment to honor the 5-file cap; tracked as part of LLR-005.2 (future increment, security defense-in-depth).

4. **CR-006 NOT closed.** The phase-2 review CR-006 calls for adding `~/.venv`, `~/venv`, `~/.local`, and `~/AppData/Local/Programs/Python` to the demotion list. My implementation follows LLR-012.1 exactly as written in the requirements doc, which does NOT include venv paths. Closing CR-006 would require updating both the LLR-012.1 statement in `01-requirements.md` AND the implementation — too many file edits to fit in this increment's 5-file budget. CR-006 stays open for a follow-up.

5. **Symlink TC on Windows.** TC-020b uses `os.symlink` which on Windows requires Developer Mode or `SeCreateSymbolicLinkPrivilege`. The TC body falls through to `pytest.skip` when symlink creation fails. The `..`-segment branch (TC-020a) covers the canonicalization invariant on every platform.

6. **Test-isolation pattern.** Pytest's `tmp_path` on Windows lives under `%LOCALAPPDATA%\Temp`, which would trip the new LLR-012.1 windows-localappdata predicate for any test that asserts a writable peer remains writable. The `_strip_windows_env` helper in `test_writable_peers.py` (and the inline patch in `test_tc_001`) handles this. Future tests that exercise writable peers under `tmp_path` should call this helper.

## 6 · Pending items

The following remain explicitly **NOT covered** by this increment:

- **LLR-004.1** — actor passing through `save_project` for writable-peer writes (US-003).
- **LLR-005.1** — read_peer_addendums iterates writable peers identically to read-only (already true post-Increment 4; needs explicit TC-022 in a future increment).
- **LLR-005.2** — throwaway `StorageService` for peer reads is non-writable (security defense-in-depth, future increment).
- **LLR-005.3** — peer-supplied actor displayed as claim, not authority (template change to `inbox.html`).
- **LLR-013.1, LLR-013.2, LLR-013.3** — identity gate + sanitization (CR-001, CR-005).
- **LLR-010.1, LLR-010.2, LLR-011.1** — Settings page route + template + no mutating routes (US-005).
- **Open CRs** — CR-001 (HIGH security), CR-005, CR-006, CR-007, CR-008, CR-009, CR-010.

## 7 · Suggested next task

**Increment 6 — US-003 actor + inbox + identity (closes CR-001 + CR-005).**

Two practical paths the user can pick:

**Option A: full US-003 in one increment (~50 minutes, 5 files at cap):**
- Scope: LLR-004.1 (actor passing) + LLR-005.1 (read_peer_addendums iteration check, mostly already-true) + LLR-005.2 (throwaway non-writable) + LLR-005.3 (`peer · <label>: <actor (claimed)>` qualifier in `inbox.html`) + LLR-013.1 (identity gate) + LLR-013.2 (`Settings.user` sanitize) + LLR-013.3 (`_append_changelog` sanitize, closes CR-001).
- Files (estimated 5): `app/services/storage.py` (add gate + sanitize_changelog), `app/settings.py` (sanitize user), `app/templates/inbox.html` (claimed qualifier), `tests/test_identity_gate.py` (NEW), `tests/test_changelog_sanitize.py` (NEW).
- TCs (estimated 9): TC-004, TC-005, TC-013, TC-021, TC-022, TC-023, TC-024, TC-035, TC-036, TC-037.
- CRs closed: CR-001 (HIGH), CR-005 (Unicode bidi).

**Option B: split into two smaller increments (~25 + ~25 minutes):**
- Increment 6a: identity + sanitization (LLR-013.1/-013.2/-013.3) → closes CR-001, CR-005.
- Increment 6b: inbox + actor (LLR-004.1, LLR-005.1, LLR-005.2, LLR-005.3) → covers US-003 inbox surfacing.

Recommended: **Option A** — the LLRs interlock (TC-035 for LLR-013.1 needs the writable-peer fixture from Increment 5 and exercises both identity and storage gating; the sanitizer LLR-013.2/3 are tiny). Estimated effort fits within one increment.

After Increment 6: Increment 7 = US-005 Settings page (LLR-010.1, LLR-010.2, LLR-011.1) + close CR-009 (`.gitignore` recommendation in USER_GUIDE.md).

---

**Stop.** Increment 5 is complete. No Increment 6 work has begun. Awaiting user approval before proceeding.
