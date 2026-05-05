# Requirements Document — ProjStatus — Batch 2026-05-04-batch-01

> **Strict normative convention — IEEE 830 + EARS**
> - `shall` = normative, binding, verifiable requirement. **Only** inside HLR / LLR statements.
> - `should` = informative / explanatory text, **NOT binding**. **Only** outside HLR / LLR statements (rationale, description, context).
> - Any use of `should` inside an HLR / LLR statement is a **writing error** and will be flagged as a blocker in phase 2.
> - `may` = optional. `will` = future declaration or fact about an external actor.

---

## 1. Introduction

### 1.1 Purpose
This document captures the requirements for batch `2026-05-04-batch-01` of **ProjStatus**, a single-process FastAPI app that stores each project as a folder of files on disk (no database). The batch addresses three real gaps detected during a verification pass against four user-stated capabilities (see §2.6 and §2.5 for the verification result).

### 1.2 Scope
**In scope** for this batch:
- A per-peer `writable` flag in `config.toml` that allows the operator to opt a previously read-only peer root into write mode, with defensive demotion of dangerous paths (HLR-012).
- Path canonicalization on the writable-roots containment check to prevent symlink / `..` / Windows-alias traversal (LLR-003.3).
- An identity gate that rejects peer-root writes when `app.state.user` is `"unknown"` or empty (HLR-013).
- Sanitization of `Settings.user` and `_append_changelog` inputs to prevent newline forgery and markdown injection into peer files (LLR-013.2 / LLR-013.3).
- A non-mutating Settings page that surfaces the configured `data_root`, peer roots (label / path / writable / reachable), and the configured user.
- An ISO 8601 calendar-week indicator on task cards, milestone rows, and the Mermaid Gantt axis, with a documented fallback when the candidate Mermaid token is unsupported (HLR-014).

**Out of scope** for this batch:
- Editing `data_root` or any other Settings value from the web UI.
- A runtime per-peer write-mode toggle in the browser.
- Adding a notion of per-user permissions, sessions, or auth (the threat model assumes loopback-only binding — see §2.4).
- Any change to the persistence format of `project.json`, `timeline.mmd`, or the section markdown files.
- Restructuring the existing inbox addendum schema; only the verification that peer-attributed addendums continue to surface correctly under writable peers, and the new "(claimed)" qualifier for peer-supplied actor display (LLR-005.3).
- Changes to non-Mermaid renderers (HTML/PDF/PNG export beyond what week-numbering naturally affects).
- A Playwright/e2e harness or any visual-rendering test (HTML-substring assertions only — see R-007).
- Replacing the Mermaid CDN dependency (R-008) or extending Settings reachability to a real read-probe (R-006).

### 1.3 Definitions, acronyms, abbreviations
| Term | Definition |
|------|------------|
| Data root | Top-level folder that contains `projects/`, `exports/`, `project_templates/`, `document_templates/`. Configured via `PROJSTATUS_DATA_ROOT` env var or `data_root` key in `~/.config/projstatus/config.toml`. |
| Peer root | A read-only (today) reference to another user's data root. Configured via `PROJSTATUS_PEER_ROOTS` env var or `peer_roots` list in `config.toml`. Used by the inbox to surface other users' addendums. |
| Writable peer | A peer root whose `writable` flag is `true` — write paths through `StorageService` MUST be permitted on its projects. New in this batch. |
| Addendum | History record produced by `StorageService.save_project`; combines a `ProjectSnapshot` with unified diffs and a recorded `actor`. Stored as `history/<timestamp>.json` plus a human-readable `.md`. |
| Actor | The username recorded on each addendum and CHANGELOG.md line. Resolved by `current_actor(request)` from `app.state.user`. |
| ISO 8601 week | Monday-start week numbering where week 01 is the week containing the year's first Thursday. Output range `W01`–`W53`. Matches Python `date.isocalendar()`. Note: two consecutive Mondays in late December can map to two different ISO years (e.g., 2024-12-30 is `2025-W01`; 2025-12-29 is `2026-W01`) because the ISO year follows the Thursday rule rather than the calendar year. |
| HLR | High-Level Requirement — IEEE 830 EARS statement at system-behavior level. |
| LLR | Low-Level Requirement — refinement of an HLR at component / file level. |

### 1.4 References
- `CLAUDE.md` (repo root) — architecture, storage rules, and `sync_state` invariants.
- `USER_GUIDE.md` — current user-facing tag syntax and document-template behavior.
- PR #18 — introduced per-user data root, identity attribution, and cross-folder inbox.
- IEEE Std 830-1998 — Recommended Practice for Software Requirements Specifications.
- EARS (Easy Approach to Requirements Syntax), Mavin et al. (2009).
- ISO 8601:2019 — Date and time — Representations for information interchange.

### 1.5 Document overview
- §2 captures the overall product context, user stories, locked design decisions, and the verification result that drives this batch.
- §3 contains the High-Level Requirements (HLR), one or more per US, in EARS form.
- §4 decomposes each HLR into Low-Level Requirements (LLR), traceable upward.
- §5 enumerates the validation method and acceptance criteria for every HLR/LLR.
- §6 holds appendices (decisions log, open risks).

---

## 2. Overall description

### 2.1 Product perspective
ProjStatus is a server-side-rendered Jinja2 app over FastAPI. The single writer for the project filesystem is `app/services/storage.py::StorageService`. Cross-folder collaboration today happens via "peer roots" — read-only references to other users' data roots whose addendums are merged into the local `/inbox`. This batch extends that mechanism in two narrow ways (writable peers, calendar-week metadata) and adds a single read-only surface (the Settings page) so an operator can quickly verify their machine-level configuration without leaving the app.

### 2.2 Product functions
The capabilities introduced in this batch are:
1. Per-peer write enable in configuration. The operator marks a specific peer root writable; from then on, mutations on that peer's projects are permitted through the same `StorageService` code path used for own projects.
2. Read-only Settings page. A new route renders the resolved `data_root`, the list of peer roots (label, path, writable, reachable), and the configured user, all derived from `app.state` at request time.
3. ISO 8601 calendar-week indicator. Task cards, milestone rows, and the Gantt axis surface the week number for the relevant date(s), formatted as `Wnn`.

### 2.3 User characteristics
- **Operator (single user per machine).** Configures the app via env vars and `~/.config/projstatus/config.toml`. Reads/writes their own projects. Reads peer projects in the inbox.
- **Cross-folder collaborator.** Another operator on a synced/shared filesystem (OneDrive, Dropbox, etc.) whose data root is mounted as a peer root on this machine. Today read-only; this batch adds the option to opt that peer into write mode locally.

### 2.4 Constraints
- No database — every change is required to flow through `StorageService.save_project` to keep history, hashes, and CHANGELOG.md consistent.
- Cross-platform file-write rules (CLAUDE.md §"Two cross-platform file-write rules") are preserved: `_write_text` for newline normalization, `_heal_section_text` retained on read.
- The Mermaid round-trip is fragile (`mermaid.py::import_timeline` only round-trips a fixed token set); any change to the Gantt axis is constrained to not introduce new tokens that would flip `sync_state.timeline_is_app_owned` to `False` on round-trip.
- The configured `actor` continues to be attributed correctly even when writing to a peer root (the actor reflects who is operating the local app, not who owns the peer folder).
- Tests in this repo use `create_app(tmp_path)` to bypass `Settings.load()`. New tests follow that pattern; nothing in this batch hard-codes paths to the real `projects/` directory.
- **Threat model — loopback only.** ProjStatus has no auth model; this batch's threat model assumes the app is bound to a loopback interface (`127.0.0.1`). Binding to a non-loopback interface is operator responsibility and out of scope. Any HLR/LLR that exposes filesystem layout or identity (notably HLR-010 / LLR-010.1) operates under this assumption.
- **`writable_roots` is captured at startup and not re-read per request** — eliminates TOCTOU between `Settings.load()` and per-request gating.
- **Plaintext `config.toml` trust assumption.** `~/.config/projstatus/config.toml` is plaintext; the operator trusts the OS file permissions on `~/.config`. A writable peer-path entry can disclose collaborator filesystem layout. **Recommended (informative):** `chmod 600 ~/.config/projstatus/config.toml` on POSIX systems; on Windows, ensure the file inherits the user-profile ACL (default behavior). The recommendation is documented in `USER_GUIDE.md` rather than enforced by the app — this batch does not introduce a permission-check gate at startup.
- **`actor` is treated as untrusted text by downstream Markdown viewers.** Both the local app and any peer's app receive `actor` strings written by the OTHER side; viewers MUST not assume the field is sanitized at write time even though LLR-013.2 imposes minimum hardening.

### 2.5 Assumptions and dependencies

> If any assumption below fails, this batch is invalidated.

| ID | Assumption | Source |
|----|------------|--------|
| A-001 | Filesystem-level write permission already exists on any peer path the operator marks writable. ProjStatus does not perform a permission check beyond attempting the write. | Inherited from existing storage model. |
| A-002 | A writable peer's `data_root` is structurally identical to the local data root (`projects/<slug>/...`). No format migration is performed on flip. | Confirmed by `StorageService` design — same class, same path layout. |
| A-003 | The `actor` recorded on an addendum written into a peer root is the LOCAL operator, not the peer's owner. The peer's inbox (when merged back via their own peer-roots config) will correctly attribute the change to us. | Locked design decision — see §6.2. |
| A-004 | ISO 8601 is the only week scheme this batch supports. A future batch may add a configurable scheme; until then `W01..W53` is hard-coded. | Locked design decision — see §6.2. |
| A-005 | The Settings page is read-only this batch. Restart is required for any data-root change. | Locked design decision — see §6.2. |
| A-006 | Existing config files that omit the `writable` field are expected to continue loading. The binding default-`false` semantics are encoded in HLR-002, not in this assumption. | Backwards-compatibility constraint. |
| A-007 | Verification gaps detected: Feature 1 (data root) was confirmed implemented but had no UI surface; Feature 3 (inbox attribution) was confirmed implemented but only exercised under read-only peers — write-enabled peers are untested as of this batch. | Read-only verification, 2026-05-04. |
| A-008 | Adding `Wnn` text to the Mermaid `axisFormat` requires updating the existing test `tests/test_mermaid_labels.py`; the test update is in scope of this batch's validation. | Inspection of test file. |
| A-009 | Two human operators sharing one OS account (and therefore one `os.getlogin()` value) cannot be distinguished by `actor`. Addendums attribute both to the same string. Out of scope for this batch — flagged so future user stories don't silently rely on per-human attribution. | Limitation of `Settings.user` resolution. |
| A-010 | When `app.state.user` resolves to `"unknown"` or empty, writes to peer roots are rejected (HLR-013 / LLR-013.1). Writes to the local `data_root` continue unaffected — a single-user machine without identity configuration is still functional for own-projects work. | Locked design — minimal-disruption rule for unconfigured machines. |
| A-011 | The Mermaid CDN dependency loaded by `app/templates/base.html` is an existing supply-chain risk. This batch's `axisFormat` change does not introduce a new CDN dependency, but does not address the existing one either. | Out-of-batch security debt; surfaced in §6.3 R-008. |

### 2.6 Source user stories

> Connextra format: **"As a `<role>`, I want `<goal>`, so that `<benefit>`"**.
> Each US gets a unique ID `US-NNN` and must be traceable to one or more HLRs.

| ID | User Story | Source |
|----|------------|--------|
| US-001 | As an operator, I want to point ProjStatus at any folder on my machine as the data root, so that my projects can live alongside my other documents (e.g., in OneDrive) instead of inside the repo checkout. | Conversation 2026-05-04 (feature 1); already implemented in PR #18, retained for traceability of US-005. |
| US-002 | As an operator, I want to register other users' project folders as read-only by default and selectively opt specific peer folders into write mode, so that I can collaborate on a shared peer's projects without exposing every peer to accidental writes. | Conversation 2026-05-04 (feature 2); partial — read-only exists, write toggle missing. |
| US-003 | As an operator, I want the inbox activity log to surface edits made by other users on projects I have write-enabled, so that I retain a single chronological view of all changes that touch any reachable project. | Conversation 2026-05-04 (feature 3); existing inbox already attributes peer addendums via `actor` — this batch confirms the path holds for writable peers and adds the missing test coverage. |
| US-004 | As an operator, I want the ISO calendar week (e.g., `W18`) shown on task cards, milestone rows, and the Gantt axis, so that I can plan in week granularity without mentally converting from `YYYY-MM-DD`. | Conversation 2026-05-04 (feature 4); not implemented. |
| US-005 | As an operator, I want a Settings page that displays the resolved data root, the configured peer roots (with their writable state and reachability), and the configured user, so that I can verify the machine-level configuration without opening a terminal or a config file. | Derived during 2026-05-04 verification — a confirmation surface for already-implemented Feature 1. Locked design decision: read-only display only this batch. |

---

## 3. High-level requirements (HLR)

> Each HLR is an EARS statement. Allowed patterns:
>
> - **Ubiquitous:** `The <system> shall <response>.`
> - **Event-driven:** `When <trigger>, the <system> shall <response>.`
> - **State-driven:** `While <state>, the <system> shall <response>.`
> - **Optional feature:** `Where <feature is included>, the <system> shall <response>.`
> - **Unwanted behavior:** `If <unwanted condition>, then the <system> shall <response>.`
> - **Complex:** combinations of the above.

### HLR-001 — Per-peer writable flag in configuration schema
- **Traceability:** US-002
- **Statement:** The configuration loader shall accept a per-peer-root `writable` boolean field in the `peer_roots` configuration source whose value is preserved on the in-memory `Settings` object.
- **Rationale (informative):** D-001 locks write enable to `config.toml`, so the schema must carry the flag from disk to the running app without a runtime UI path.
- **Priority:** high

### HLR-002 — Default-false write safety for peer roots
- **Traceability:** US-002
- **Statement:** Where a peer-root configuration entry omits the `writable` field, the configuration loader shall resolve that peer's writable state to `false`.
- **Rationale (informative):** A-006 requires backward compatibility with existing configs, and R-002 calls for an opt-in default to limit blast radius.
- **Priority:** high

### HLR-003 — Storage write gating against peer-root writable state
- **Traceability:** US-002
- **Statement:** When a write operation through `StorageService.save_project` targets a project whose containing root is a non-writable peer root, the system shall reject the write without modifying any file on disk.
- **Rationale (informative):** The existing inbox merges peer reads only; introducing writes without a gate would let any code path corrupt a peer's data root. A rejection (rather than a silent write) makes the misconfiguration observable.
- **Priority:** high

### HLR-004 — Local actor attribution on writable-peer mutations
- **Traceability:** US-003
- **Statement:** When `StorageService.save_project` writes into a writable peer root, the system shall record the local operator (the value of `app.state.user`) as the addendum and CHANGELOG.md actor.
- **Rationale (informative):** D-005 / A-003 lock attribution to the local operator so that, when the peer subsequently configures us as a peer root, their inbox correctly identifies who made each change.
- **Priority:** high

### HLR-005 — Inbox surfaces writable-peer addendums identically to read-only peer addendums
- **Traceability:** US-003
- **Statement:** When the inbox view is rendered, the system shall include addendums from writable peer roots in the merged activity log using the same chronological merge and `peer · <label>` chip semantics already applied to read-only peer roots.
- **Rationale (informative):** Per scope, writable peers must not introduce a separate display path; a single merge keeps the chronology contract from PR #18 intact.
- **Priority:** medium

### HLR-006 — ISO 8601 week computation primitive
- **Traceability:** US-004
- **Statement:** The system shall provide a single function that, given a `date` or null input, returns its ISO 8601 calendar-week label in the form `Wnn` (where `nn` is zero-padded in the range `01`–`53`) or the empty string when the input is null.
- **Rationale (informative):** D-003 hard-codes ISO 8601 this batch; centralizing the computation prevents drift between cards, milestone rows, and the Gantt axis. Null tolerance is centralized here so callers do not pre-check `None`.
- **Priority:** high

### HLR-007 — Week chip on task cards
- **Traceability:** US-004
- **Statement:** When a task with a non-null `start_date` is rendered on the board, the system shall display its ISO week label adjacent to its date metadata, using the start-week label alone when `end_date` is null, missing, or in the same ISO week as `start_date`, and appending an `–Wmm` suffix only when `end_date` is non-null and falls in a different ISO week than `start_date`. If `end_date` precedes `start_date` (data error), then the system shall display the start-week label alone and shall not raise.
- **Rationale (informative):** R-003 was open; the "start, plus optional `–Wmm` when the task crosses a week boundary" rule preserves single-glance scanning and makes multi-week spans explicit. Tasks without a start date display no chip. The end-before-start case is treated identically to the no-end case to keep rendering total over `Task.start_date × Task.end_date`.
- **Priority:** medium

### HLR-008 — Week chip on milestone rows
- **Traceability:** US-004
- **Statement:** When a milestone row is rendered (Plan-tab milestone list and Summary), the system shall display the ISO week label corresponding to the milestone's `target_date`.
- **Rationale (informative):** A milestone has exactly one date, so the multi-week rule of HLR-007 does not apply.
- **Priority:** medium

### HLR-009 — Week labels on Gantt axis without breaking round-trip
- **Traceability:** US-004
- **Statement:** When the Mermaid timeline is rendered, the system shall include the ISO week token in the Gantt `axisFormat` value such that the rendered axis displays `Wnn` and no token outside the existing `axisFormat` line conveys the week.
- **Rationale (informative):** D-004 requires that `mermaid.py::import_timeline` continue to mark the timeline app-owned; only `axisFormat` survives the parser whitelist while still producing visible week labels.
- **Priority:** high

### HLR-010 — Read-only Settings page route
- **Traceability:** US-005
- **Statement:** The system shall expose an HTTP `GET` route that renders a Settings page containing the resolved `data_root`, the configured `peer_roots` (label, path, writable, reachable), and the configured `user`, sourced from `app.state` at request time.
- **Rationale (informative):** D-002 / A-005 lock the page to a read view; rendering from `app.state` avoids re-running `Settings.load()` per request.
- **Priority:** medium

### HLR-011 — No mutating routes against Settings data
- **Traceability:** US-005
- **Statement:** If an HTTP request to `/settings` uses a method other than `GET` or `HEAD`, then the system shall not provide a route handler for that combination.
- **Rationale (informative):** D-002 explicitly forbids edits this batch; the cleanest enforcement is the absence of any handler. The framework default response (`405 Method Not Allowed`) is then a verifiable consequence of the absent handler — TC-011 asserts this consequence directly via `TestClient`.
- **Priority:** medium

### HLR-012 — Defensive guardrails on writable peer paths
- **Traceability:** US-002
- **Statement:** If a `[[peer_roots]]` entry resolves to `/`, a filesystem root, the operator's home directory, or any ancestor of `data_root`, then the system shall demote that entry's `writable` flag to `false` at startup and shall emit a stderr warning identifying the entry by label.
- **Rationale (informative):** D-001's "no runtime UI" places the entire blast-radius decision into a plaintext config file. A typo or misunderstanding (e.g., `path = "/"`) would otherwise mount the entire filesystem as writable. Demotion (rather than refusal to start) keeps the operator in a working state with the dangerous entry visibly disarmed.
- **Priority:** high

### HLR-013 — Identity-required writes against peer roots
- **Traceability:** US-003
- **Statement:** If `app.state.user` resolves to `"unknown"` or the empty string, then the system shall reject any `save_project` call whose target path lies under a writable peer root and shall return an actionable error to the caller, while permitting writes that target paths under `data_root`.
- **Rationale (informative):** A-003 / D-005 lock the recorded actor to the local operator. Writing into another operator's data root with an unidentified actor silently breaks US-003 (the inbox attribution contract). Local-data-root writes are exempted so an unconfigured single-user machine continues to function for own-projects work (A-010). When both LLR-003.1 (writable-roots check) and LLR-013.1 (actor check) would trigger for the same call (e.g., a non-writable peer + actor `"unknown"`), LLR-003.1 takes precedence — see N-S-001 fix and the gate-ordering rationale on LLR-013.1.
- **Priority:** high

### HLR-014 — Mermaid `axisFormat` token compatibility
- **Traceability:** US-004
- **Statement:** Where the ISO-week token chosen by `render_timeline` is unsupported by the Mermaid version pinned in `app/templates/base.html`, the system shall fall back to a documented alternative token whose rendered output also yields `Wnn` and shall not emit any non-axis line that would flip `sync_state.timeline_is_app_owned` to `False`.
- **Rationale (informative):** Phase-1 verification revealed that the candidate `%V` token may not be supported on every Mermaid CDN version pinned in `base.html` (R-005). This HLR makes the fallback path a binding requirement rather than a phase-3 implementer's choice.
- **Priority:** high

---

## 4. Low-level requirements (LLR)

> Each LLR decomposes an HLR into a verifiable property at the implementation level.
> Same EARS regime. ID format: `LLR-<HLR>.<M>`.

### LLR-001.1 — Extend `_resolve_peer_roots` return shape
- **Traceability:** HLR-001
- **Statement:** The function `app/settings.py::_resolve_peer_roots` shall return a list of `(label, path, writable)` tuples, where `writable` is parsed from the `writable` key of each TOML `peer_roots` entry and coerced to `bool`.
- **Acceptance criteria (informative):**
  - Existing TOML entries with `{label, path}` only continue to load.
  - Entries with `writable = true` produce `writable=True` in the tuple.
  - The env-var format (`label=path,...`) ignores writable (always `False`) since the env path has no syntax for it.

### LLR-001.2 — Propagate writable flag through `Settings.peer_roots`
- **Traceability:** HLR-001
- **Statement:** The `Settings` dataclass in `app/settings.py` shall expose `peer_roots` as `list[tuple[str, Path, bool]]` and `app.main.create_app` shall store the resolved triples on `app.state.peer_roots`.
- **Acceptance criteria (informative):**
  - `app.state.peer_roots[i][2]` is a `bool` for every configured peer.
  - Tests that pass `root_dir` to `create_app(root_dir)` continue to receive an empty `peer_roots` list.

### LLR-002.1 — Default writable to `False` when key missing
- **Traceability:** HLR-002
- **Statement:** If a TOML peer-root entry omits the `writable` key, then `_resolve_peer_roots` shall assign `writable=False` for that entry.
- **Acceptance criteria (informative):**
  - A TOML fixture with `[[peer_roots]] label="x" path="/tmp"` parses with writable false.
  - Malformed values (non-bool) coerce to false rather than raising.

### LLR-003.1 — Reject writes targeting non-writable peers
- **Traceability:** HLR-003
- **Statement:** When `StorageService.save_project` is invoked with a `project_dir` that does not lie under `data_root` and does not lie under any peer root whose writable flag is `True`, the service shall raise a domain-specific `PermissionError` and shall not invoke `_write_text` for any file.
- **Acceptance criteria (informative):**
  - A test that points a `StorageService` at a peer root with `writable=False` and calls `save_project` raises and leaves the project directory byte-identical.
  - Writes against `data_root` itself are unaffected.

### LLR-003.2 — Plumb writable peer roots into `StorageService`
- **Traceability:** HLR-003
- **Statement:** The constructor of `StorageService` shall accept a `writable_roots: list[Path]` argument (defaulting to `[data_root]`); `app/main.py::create_app` shall pass `[data_root, *writable_peer_paths]`.
- **Acceptance criteria (informative):**
  - The check in LLR-003.1 uses path containment against this list.
  - Existing call sites that pass only `data_root` continue to work.

### LLR-003.3 — Path canonicalization on writable-roots check
- **Traceability:** HLR-003
- **Statement:** Before performing the writable-roots containment check (LLR-003.1), `StorageService.save_project` shall call `Path.resolve(strict=False)` on every entry of `writable_roots` and on `project_dir`, and shall use `Path.is_relative_to(resolved_root)` (rather than string-prefix comparison) to determine containment.
- **Acceptance criteria (informative):**
  - A symlink inside a writable peer pointing OUT of the peer (e.g., `peer-alice/projects/evil → /etc/cron.d/`) is rejected because the resolved `project_dir` is not relative to any resolved entry of `writable_roots`.
  - A `..` segment in the project `slug` cannot escape the peer root.
  - On Windows, an 8.3 short-name alias of the writable root resolves to the same long form as the long-form entry, so containment holds.
  - The check uses `realpath`-equivalent semantics; junction points / reparse points are followed, not bypassed.

### LLR-004.1 — Pass local actor on writable-peer save
- **Traceability:** HLR-004
- **Statement:** Every `save_project` call in `app/main.py` shall continue to pass `actor=current_actor(request)`, and `StorageService.save_project` shall not override the actor based on which root the project lives under.
- **Acceptance criteria (informative):**
  - A test that writes to a writable peer asserts the resulting addendum's `actor` equals `app.state.user`.
  - The CHANGELOG.md line written into the peer root contains the local username.

### LLR-005.1 — Include writable-peer addendums in `read_peer_addendums`
- **Traceability:** HLR-005
- **Statement:** The function `storage.read_peer_addendums(peer_roots, limit)` shall iterate over all configured peer roots regardless of their writable flag and merge their addendums into the inbox stream.
- **Acceptance criteria (informative):**
  - A peer root with `writable=True` contributes the same `(peer_label, slug, addendum)` triples it would when `writable=False`.
  - The `peer · <label>` chip is rendered for both writable and non-writable peer rows.

### LLR-005.2 — Throwaway `StorageService` for peer reads is non-writable
- **Traceability:** HLR-005
- **Statement:** The throwaway `StorageService` instances created inside `read_peer_addendums` for the sole purpose of listing a peer's addendums shall be constructed with `writable_roots=[]` to ensure no accidental write path through a peer-only service.
- **Acceptance criteria (informative):**
  - A unit test that obtains the throwaway `StorageService` and calls `save_project` on it raises the same `PermissionError` (LLR-003.1) regardless of the peer's writable state.
  - The change is invisible to the caller of `read_peer_addendums` (return shape unchanged).

### LLR-005.3 — Peer-supplied actor displayed as claim, not authority
- **Traceability:** HLR-005
- **Statement:** The inbox template `app/templates/inbox.html` shall render a peer-row's actor field as `peer · <label>: <actor (claimed)>` (or an equivalent visually-distinct format) so that a peer addendum's `actor` value cannot visually masquerade as a local-app actor.
- **Acceptance criteria (informative):**
  - When a peer addendum's `actor` field equals the local `app.state.user`, the rendered HTML for that row contains the `peer · <label>` prefix and a "(claimed)" or equivalent qualifier — never just the bare actor string.
  - Own-app rows (no peer label) continue to display the actor without the qualifier.
  - The qualifier text is greppable so TC-029 can assert it.

### LLR-006.1 — `iso_week_label(d)` helper
- **Traceability:** HLR-006
- **Statement:** A new function `iso_week_label(d: date) -> str` in `app/utils.py` shall return `f"W{d.isocalendar().week:02d}"` for a non-null `date` and the empty string for `None`.
- **Acceptance criteria (informative):**
  - `iso_week_label(date(2026, 1, 1))` returns `"W01"`.
  - `iso_week_label(date(2025, 12, 29))` returns `"W01"` (ISO year 2026 begins on Mon 2025-12-29).
  - `iso_week_label(date(2024, 12, 29))` returns `"W52"` (Sunday-Monday boundary case).
  - `iso_week_label(date(2020, 12, 31))` returns `"W53"`.
  - `iso_week_label(None)` returns `""` and does not raise.

### LLR-007.1 — Render week chip on task card template
- **Traceability:** HLR-007
- **Statement:** The task-card partial in `app/templates/partials/project_board.html` shall render a `<span class="week-chip">` containing `iso_week_label(start_date)` whenever `start_date` is non-null, suffixed with `–Wmm` when `end_date` is non-null and `iso_week_label(end_date) != iso_week_label(start_date)`, and shall render no chip when `start_date` is null.
- **Acceptance criteria (informative):**
  - **Positive cases (substring assertions):**
    - A task with `start_date=2026-04-27, end_date=2026-04-29` renders HTML containing `W18`.
    - A task with `start_date=2026-04-27, end_date=2026-05-04` renders HTML containing `W18–W19`.
    - A task with `start_date=2026-04-27, end_date=None` renders HTML containing `W18` (no suffix).
    - A task with `start_date=2026-05-04, end_date=2026-04-27` (end before start) renders HTML containing `W19` (start-only, no suffix, no exception).
  - **Negative case (substring negation):**
    - A task with `start_date=None` renders task-card HTML that does NOT contain the substring `class="week-chip"` — the no-chip path is verified by the absence of the chip element, not just the absence of `Wnn` text.

### LLR-007.2 — Expose `iso_week_label` to Jinja
- **Traceability:** HLR-007
- **Statement:** `create_app` in `app/main.py` shall register `iso_week_label` as a Jinja global so templates can call it without a per-route context injection.
- **Acceptance criteria (informative):**
  - Templates can call `{{ iso_week_label(task.start_date) }}` directly.
  - No route handler is modified to add the helper to its context.

### LLR-008.1 — Render week chip on milestone rows
- **Traceability:** HLR-008
- **Statement:** The milestone-row partial `app/templates/partials/_milestones_list.html` shall render `iso_week_label(milestone.target_date)` next to the milestone's date when `target_date` is set.
- **Acceptance criteria (informative):**
  - A milestone with `target_date=2026-05-04` renders `W19`.
  - A milestone without `target_date` renders no chip and does not raise.

### LLR-009.1 — Week token confined to `axisFormat`
- **Traceability:** HLR-009
- **Statement:** The function `app/services/mermaid.py::render_timeline` shall emit the ISO-week token only inside the `axisFormat` line of the rendered Mermaid source, and shall not emit any per-task or per-milestone token conveying week information.
- **Acceptance criteria (informative):**
  - The string `W` (used as the week prefix) appears in the rendered Mermaid source only on the line beginning with `axisFormat`.
  - `import_timeline(render_timeline(p))` returns `supported=True` for a project with tasks and milestones.
  - Existing fixtures in `tests/test_mermaid_labels.py` are updated, not broken by, this change.

### LLR-009.2 — Round-trip preserves `timeline_is_app_owned`
- **Traceability:** HLR-009
- **Statement:** For a project whose `timeline.mmd` is app-owned (i.e., produced by `render_timeline`), the round-trip `render_timeline → import_timeline → render_timeline` shall preserve `sync_state.timeline_is_app_owned=True` (the fourth tuple element of `import_timeline` returning `True`) and shall produce string-equal Mermaid text.
- **Acceptance criteria (informative):**
  - The actual signature of `import_timeline` is `(project: Project, timeline_text: str) -> tuple[Project, list[str], list[str], bool]` (per `app/services/mermaid.py`). The two `list[str]` elements are `imported_msgs` (success messages) and `errors` (unsupported-line messages); the fourth element is `ok` (the `supported` flag).
  - **Important — `import_timeline` mutates the input `Project` in place** (returns the same object). To detect a real round-trip regression the test MUST pass a **deep copy** of the project to `import_timeline` so the comparison against the rendered original is non-tautological:
    ```python
    rendered = render_timeline(p)
    imported, _imported_msgs, _errors, ok = import_timeline(deepcopy(p), rendered)
    assert ok is True
    assert render_timeline(imported) == rendered  # plain string equality, no normalisation
    ```
  - The check holds for the standard fixture used by `tests/test_mermaid_labels.py::test_render_timeline_round_trip_preserves_titles_and_dates`. Updated to address phase-2 iter-3 findings A-1 (CR-002 — round-trip tautology) and A-2 (CR-004 — list naming).

### LLR-010.1 — `GET /settings` route
- **Traceability:** HLR-010
- **Statement:** A new route `GET /settings` in `app/main.py` shall render a Jinja template displaying `app.state.data_root`, `app.state.peer_roots` (each as label / path / writable / reachable, where reachable is computed via `Path.is_dir()` after `os.path.realpath` containment), and `app.state.user`.
- **Acceptance criteria (informative):**
  - Response status is 200 and the body contains the literal `data_root` path text.
  - For a peer whose path does not exist on disk, the rendered HTML row contains the literal substring `unreachable`.
  - For a peer with `writable=True`, the rendered HTML row contains the literal substring `RW`.
  - For a peer with `writable=False`, the rendered HTML row contains the literal substring `RO`.
  - The page is reachable from the sidebar via `build_sidebar_context`.

### LLR-010.2 — Settings template lives under `app/templates/settings.html`
- **Traceability:** HLR-010
- **Statement:** The template `app/templates/settings.html` shall be rendered through `render_template` so the sidebar/breadcrumb shell remains consistent with other pages, and shall contain no `<form>`, `<input>`, `<button type="submit">`, or `method="post"` markup.
- **Acceptance criteria (informative):**
  - Page extends `base.html` (verifiable by inspection of the first non-comment line).
  - Case-insensitive `grep -i "<form"` against the template returns zero matches.
  - Case-insensitive `grep -iE "<input|<button[^>]*type=.submit|method=.post"` returns zero matches.

### LLR-011.1 — No mutating route handlers on `/settings`
- **Traceability:** HLR-011
- **Statement:** The codebase shall not register `POST`, `PUT`, `PATCH`, or `DELETE` handlers whose path equals `/settings` or matches `/settings/*`.
- **Acceptance criteria (informative):**
  - A `grep` of `app/main.py` for `"/settings"` finds only `@app.get` decorators.
  - A `TestClient` request with each of `POST`, `PUT`, `PATCH`, `DELETE` against `/settings` returns status `405`.

### LLR-012.1 — Detect and demote dangerous writable-peer paths
- **Traceability:** HLR-012
- **Statement:** Inside `Settings.load`, in a post-pass that occurs AFTER `_resolve_peer_roots` returns its candidate triples AND AFTER `data_root` has been resolved (because the demotion needs `data_root` to test "ancestor of `data_root`", a value `_resolve_peer_roots` does not see), the loader shall iterate the writable entries and, for any whose resolved `Path.resolve(strict=False)` matches any of the dangerous-path predicates below, set `writable=False` and emit one stderr warning per demoted entry.
- **Dangerous-path predicates (block list):**
  - Equal to `Path("/")` (POSIX root) or any Windows drive root (`Path("C:\\")`, `Path("D:\\")`, …).
  - Equal to `Path.home()` itself.
  - An ancestor of the resolved `data_root` (per `data_root.is_relative_to(candidate)`; note that `data_root.is_relative_to(data_root) is True`, so a peer entry equal to `data_root` is also demoted).
  - Equal to or an ancestor of any of the following sensitive home-directory children, when resolvable on the host OS:
    - POSIX: `Path.home() / ".ssh"`, `~/.aws`, `~/.config`, `~/.gnupg`, `~/.kube`, `~/.docker`, `/etc`, `/usr`, `/var`, `/bin`, `/sbin`.
    - Windows: `%APPDATA%`, `%LOCALAPPDATA%`, `%PROGRAMDATA%` (resolved via `os.environ`; if any env var is unset, the entry is skipped silently).
- **Warning format:** `WARNING: peer-root '<label>' demoted to read-only — path <resolved-path> is unsafe to mark writable (matched: <predicate-name>)`.
- **Acceptance criteria (informative):**
  - A `[[peer_roots]] label="bad" path="/" writable=true` entry resolves to `(label="bad", path=Path("/"), writable=False)` after `Settings.load`.
  - The same demotion occurs for `~`, `~/.ssh`, `~/.aws`, `data_root.parent`, and a Windows `C:\` drive root.
  - A non-dangerous writable peer (e.g., `~/work/peer-alice` where `peer-alice` is NOT under any sensitive child) is left untouched.
  - The warning is emitted exactly once per demoted entry per process lifetime.
  - The warning text contains the matched predicate name (e.g., `home-dir`, `ssh-credentials`, `data-root-ancestor`) so phase-4 inspection can grep it.

### LLR-013.1 — Reject writes to peer roots when actor is missing
- **Traceability:** HLR-013
- **Statement:** The actor-missing check in `StorageService.save_project` shall execute AFTER the writable-roots containment check (LLR-003.1) and shall, if `actor` is empty, `None`, or equals the literal string `"unknown"`, AND `project_dir` resolves under a writable peer root (NOT under `data_root`), raise `PermissionError` with a message identifying the peer label and the missing-actor cause, without modifying any file on disk. Both checks shall execute before any call to `_write_text`.
- **Gate ordering rationale (informative):** when both LLR-003.1 (writable-roots check) and LLR-013.1 (actor check) would trigger for the same call, LLR-003.1 wins — a non-writable target should produce a writability error regardless of actor state. This keeps the error message deterministic for phase-3 test assertions.
- **Acceptance criteria (informative):**
  - `save_project(..., actor="unknown")` against a writable peer raises `PermissionError` and leaves the project byte-identical (SHA-256 of `project.json` unchanged).
  - `save_project(..., actor="unknown")` against `data_root` succeeds (own-projects work continues).
  - `save_project(..., actor="unknown")` against a NON-writable peer raises with a writability-error message (NOT an actor-error message), confirming LLR-003.1 fired first.
  - The actor-error message contains the peer label and the substring `actor` so phase-3 test assertions can grep it.

### LLR-013.2 — Sanitize `Settings.user`
- **Traceability:** HLR-013
- **Statement:** The function that resolves `Settings.user` (env > config.toml > `os.getlogin()` > `"unknown"`) shall, for each candidate source, strip control characters (`\x00`–`\x1f`, `\x7f`) and Unicode bidirectional override characters (U+202A LRE, U+202B RLE, U+202C PDF, U+202D LRO, U+202E RLO, U+2066 LRI, U+2067 RLI, U+2068 FSI, U+2069 PDI), reject the source by falling through to the next if the original (pre-strip) string contained `\r` or `\n`, and cap the resolved value at 64 characters.
- **Sanitizer chain rationale (informative):** the sanitizer never synthesizes the literal string `"unknown"` — it only strips/caps or falls through. The unconfigured-default `"unknown"` arrives only via the final source in the chain (after `os.getlogin()` itself fails or returns empty), and the gate in LLR-013.1 handles that default. Thus LLR-013.2 + LLR-013.1 form a clean producer-consumer pair: sanitizer narrows what the recorded actor CAN be; gate decides whether to trust it for peer writes.
- **Acceptance criteria (informative):**
  - `PROJSTATUS_USER="alice\nfake-actor"` falls through (the env source is rejected) and the user resolves from the next source.
  - `PROJSTATUS_USER="alice"` resolves to `"alice"`.
  - `PROJSTATUS_USER="alice‮evil"` resolves to `"aliceevil"` (the U+202E RLO override is stripped, length cap not yet hit).
  - A 200-character env value is truncated to the first 64 characters.
  - A null-byte (`\x00`) in the env value is stripped before length-capping.
  - The sanitizer never returns the literal `"unknown"` from a non-fall-through source — it only returns sanitized non-empty strings or falls through.

### LLR-013.3 — Sanitize CHANGELOG.md headline and note
- **Traceability:** HLR-013
- **Statement:** The function `_append_changelog` shall, for the `headline` and `note` fields, apply the following operations in this exact order: (1) replace any `\r` or `\n` with a single space; (2) replace pipe (`|`), bracket (`[`, `]`), and angle-bracket (`<`, `>`) characters with their HTML-equivalent entities (`&#124;`, `&#91;`, `&#93;`, `&lt;`, `&gt;`); (3) cap each field at 200 characters AFTER escaping (so the entity sequences themselves count toward the 200-char budget). The escaped, capped fields are then joined with the existing separator.
- **Ordering rationale (informative):** the cap-after-escape ordering means the disk-resident line length is the hard ground truth — a 200-char input ending in `[` becomes `<…>&#91;` which is still ≤ 200 chars total. If the cap ran before escape, the line could grow unpredictably as escapes were inserted.
- **Acceptance criteria (informative):**
  - A `note` containing `[click](javascript:alert(1))` is written to CHANGELOG.md as `&#91;click&#93;(javascript:alert(1))` — the markdown-link syntax is broken.
  - A `note` containing `<script>alert(1)</script>` is written as `&lt;script&gt;alert(1)&lt;/script&gt;` — HTML-tag injection is broken even if a downstream viewer renders the Markdown to HTML.
  - A `note` containing 1000 `\n` characters is collapsed to 1000 spaces, then has nothing to escape, then is capped at 200, leaving a 200-space string.
  - A pipe in the project name is replaced with `&#124;` so a downstream Markdown table renderer cannot be tricked into a column split.
  - A 250-char input that contains 50 `[` and 50 `]` characters becomes (after escape) ~700 chars and is then capped to 200 — the cap is enforced post-escape.

### LLR-014.1 — Verified Mermaid token with documented fallback
- **Traceability:** HLR-014
- **Statement:** The chosen `axisFormat` token shall be exposed as the module-level constant `ISO_WEEK_AXIS_TOKEN: Final[str]` in `app/services/mermaid.py`; both `render_timeline` and the test fixtures shall import the constant; if the candidate token (`%V`) renders literally rather than as a week number on the Mermaid version pinned in `app/templates/base.html`, the constant value shall be switched to a documented fallback token whose rendered output yields `Wnn`, and the chosen token (whichever it is) shall produce a `render_timeline` output that round-trips through `import_timeline` with the `ok` flag `True`.
- **Acceptance criteria (informative):**
  - **Always (regardless of which token was chosen):** the rendered Mermaid `axisFormat` line of `render_timeline(p)` contains the literal substring `W` (the week-prefix that survives Mermaid's strftime-equivalent expansion).
  - **Always:** `import_timeline(p, render_timeline(p))[3] is True` — the round-trip's `ok` flag (4th tuple element) confirms the new axis line did not introduce any token that would flip `timeline_is_app_owned` to `False`.
  - **Conditional on fallback chosen — machine-readable via the constant:** the test imports `ISO_WEEK_AXIS_TOKEN` and asserts `if ISO_WEEK_AXIS_TOKEN != "%V": assert "%V" not in axisFormat_line`. The conditional is no longer dependent on parsing the increment review packet at runtime (CR-003).
  - The fallback decision (kept-`%V` vs which alternative) is recorded BOTH as the constant value in `mermaid.py` and as a one-line note in the phase-3 increment review packet.

---

## 5. Validation strategy

### 5.1 Methods
- **Test:** automated execution (unit / integration / e2e). Default for LLR.
- **Demo:** observed execution of behavior. Useful for UX-oriented HLRs.
- **Inspection:** static review of code or document. Useful for structural requirements.
- **Analysis:** formal or quantitative reasoning (performance, complexity, security).

### 5.2 Coverage table

> **Convention.** Each HLR is paired with a behavioural acceptance TC (TC-001..TC-014); each LLR is paired with an implementation-detail TC (TC-015..TC-038). The HLR-level TC verifies the system-level outcome (what the user observes); the LLR-level TC pins the file/function path taken to produce it. Both layers are required for traceability — neither is redundant.

**HLR-level acceptance TCs**

| Requirement | Method | Test Case ID | Notes |
|-------------|--------|--------------|-------|
| HLR-001 | test (unit) | TC-001 | `_resolve_peer_roots` accepts `writable` from a TOML peer entry and returns it on the resolved triple. |
| HLR-002 | test (unit) | TC-002 | Omitting `writable` from a TOML peer entry resolves to `False`. |
| HLR-003 | test (integration) | TC-003 | `save_project` against a non-writable peer raises `PermissionError` and leaves files byte-identical. |
| HLR-004 | test (integration) | TC-004 | Addendum `actor` equals `app.state.user` when writing into a writable peer. |
| HLR-005 | test (integration) | TC-005 | `/inbox` lists a writable-peer addendum with the `peer · <label>` chip and the local user as actor. |
| HLR-006 | test (unit) | TC-006 | `iso_week_label(date(2026,4,27))` returns `"W18"`. |
| HLR-007 | test (integration) | TC-007 | A board-rendered task with `start_date=2026-04-27, end_date=2026-04-29` produces HTML containing `W18`. |
| HLR-008 | test (integration) | TC-008 | A board-rendered milestone with `target_date=2026-05-04` produces HTML containing `W19`. |
| HLR-009 | test (unit) | TC-009 | `render_timeline(p)` for a fixture project produces an `axisFormat` line whose week token is contained in the line. |
| HLR-010 | test (integration) | TC-010 | `GET /settings` returns 200 and the body contains `data_root`, every peer label, and the user string. |
| HLR-011 | test (integration) | TC-011 | `TestClient` requests with each of `POST`, `PUT`, `PATCH`, `DELETE` against `/settings` each return status 405. |
| HLR-012 | test (integration) | TC-012 | A `[[peer_roots]] path="/" writable=true` entry resolves to `writable=False` after `Settings.load` and emits one stderr warning. |
| HLR-013 | test (integration) | TC-013 | Calling `save_project(actor="unknown")` against a writable peer raises `PermissionError`; calling against `data_root` succeeds. |
| HLR-014 | test (unit) | TC-014 | The `axisFormat` line of `render_timeline(p)` contains the literal `W`; `import_timeline(fresh, render_timeline(p))[3] is True`; the test imports `ISO_WEEK_AXIS_TOKEN` from `app.services.mermaid` and asserts `if ISO_WEEK_AXIS_TOKEN != "%V": assert "%V" not in axisFormat_line`. |

**LLR-level implementation-detail TCs**

| Requirement | Method | Test Case ID | Notes |
|-------------|--------|--------------|-------|
| LLR-001.1 | test (unit) | TC-015 | `_resolve_peer_roots` returns `(label, path, writable)` triples for TOML and env-var sources; env-var path always sets `writable=False`. |
| LLR-001.2 | test (unit) | TC-016 | `create_app(tmp_path)` stores `[]` on `app.state.peer_roots`; `create_app()` with peer env stores triples; per-peer `bool` type assertion. |
| LLR-002.1 | test (unit) | TC-017 | TOML entry with no `writable` key → `False`; non-bool value (`"yes"`, `1`) coerces to `False`. |
| LLR-003.1 | test (unit) | TC-018 | Path-containment check rejects non-writable peer; SHA-256 of `project.json` unchanged on rejection. |
| LLR-003.2 | test (unit) | TC-019 | `StorageService(writable_roots=[...])` accepts the new kwarg; default is `[data_root]`. |
| LLR-003.3 | test (integration) | TC-020 | A symlinked `peer/projects/evil → /tmp/escape` is rejected; `..` segment in `slug` is rejected after `Path.resolve`. |
| LLR-004.1 | test (integration) | TC-021 | Addendum `actor` and the CHANGELOG.md line both contain the local username when writing into a writable peer. |
| LLR-005.1 | test (unit) | TC-022 | `read_peer_addendums` returns the same triples for `writable=True` and `writable=False` peers. |
| LLR-005.2 | test (unit) | TC-023 | The throwaway `StorageService` from `read_peer_addendums` raises `PermissionError` on any `save_project` call regardless of peer's writable state. |
| LLR-005.3 | test (integration) | TC-024 | When a peer addendum's `actor` equals the local user, the inbox HTML row contains both `peer · <label>` and a "(claimed)" qualifier. |
| LLR-006.1 | test (unit) | TC-025 | Year-boundary cases per §5.4; `iso_week_label(None)` returns `""` and does not raise. |
| LLR-007.1 | test (integration) | TC-026 | The four positive-case fixtures in §5.4.B render the correct chip text (substring assertion). The one negative-case fixture (`start_date=None, end_date=2026-04-29`) renders task-card HTML that does NOT contain `class="week-chip"`. |
| LLR-007.2 | test (integration) | TC-027 | A template directly invoking `{{ iso_week_label(d) }}` (without the route adding it to context) renders the expected week label. |
| LLR-008.1 | test (integration) | TC-028 | Milestone `target_date=2026-05-04` renders `W19`; null `target_date` renders no chip and no exception. |
| LLR-009.1 | test (unit) | TC-029 | The literal `W` character appears in `render_timeline(p)` only on the `axisFormat` line; per-task and per-milestone lines contain no `W`. |
| LLR-009.2 | test (unit) | TC-030 | `rendered = render_timeline(p)`; `imported, _imported_msgs, _errors, ok = import_timeline(deepcopy(p), rendered)`; `assert ok is True`; `assert render_timeline(imported) == rendered` — plain string equality, no normalisation. The deepcopy is load-bearing (CR-002). |
| LLR-010.1 | test (integration) | TC-031 | Response includes literal `data_root` path; rows for writable + read-only peers contain `RW` and `RO` substrings respectively; missing-path peer's row contains `unreachable`. |
| LLR-010.2 | inspection | TC-032 | `grep -i "<form"` of `app/templates/settings.html` returns zero matches; first inheritance line is `{% extends "base.html" %}`. |
| LLR-011.1 | test (integration) | TC-033 | `POST /settings` returns status 405 (and the same for `PUT`, `PATCH`, `DELETE` — covered jointly with TC-011). |
| LLR-012.1 | test (unit) | TC-034 | A writable entry `path="/"` is demoted; same for `Path.home()`, `data_root.parent`, Windows drive root; warning emitted exactly once per demoted entry per process. |
| LLR-013.1 | test (integration) | TC-035 | (a) `save_project(actor="unknown", project_dir=writable_peer/...)` raises `PermissionError` whose message contains the peer label and the substring `actor`. (b) `save_project(actor="unknown", project_dir=data_root/...)` succeeds AND produces an addendum whose `actor=="unknown"`. (c) `save_project(actor="unknown", project_dir=non_writable_peer/...)` raises `PermissionError` whose message references writability (NOT the actor) — confirms LLR-003.1 fires before LLR-013.1. |
| LLR-013.2 | test (unit) | TC-036 | With `PROJSTATUS_USER="alice\nfake"` AND a `config.toml [user] name="bob"`, the resolved user equals `"bob"` (env source rejected, config source taken). 200-char input is capped at 64. `\x00` and U+202E RLO stripped. The sanitizer never returns the literal `"unknown"` from a non-fall-through source. |
| LLR-013.3 | test (unit) | TC-037 | `_append_changelog(headline="x[a](js:1)y", note="<script>alert(1)</script>")` writes a CHANGELOG.md line containing `&#91;a&#93;` and `&lt;script&gt;`. Multi-newline input collapses to spaces, then escape, then cap at 200 (post-escape) — verified by feeding 250-char input with 50 `[`/50 `]` and asserting the disk-resident field is exactly 200 chars. |
| LLR-014.1 | test (unit) | TC-038 | The `axisFormat` line of `render_timeline(p)` contains the literal `W`. `import_timeline(fresh, render_timeline(p))[3] is True`. The test imports `ISO_WEEK_AXIS_TOKEN` from `app.services.mermaid`; if `ISO_WEEK_AXIS_TOKEN != "%V"` (fallback chosen), assert `"%V" not in axisFormat_line` — otherwise the `%V`-absence assertion is N/A and skipped. |

**Method distribution:** test (unit) = 19 · test (integration) = 18 · inspection = 1 · demo = 0 · analysis = 0 · test (e2e) = 0 · **Total = 38** (= 14 HLR + 24 LLR). [Recounted in phase-2 iteration-2 review; an earlier draft had `unit=18, integration=19` swapped — the row-by-row count is now ground-truth.]

### 5.4 Test data fixtures

#### A. ISO-week boundary cases for TC-006, TC-014, TC-025, TC-029, TC-030, TC-038

| Date | Weekday | Expected `iso_week_label` | Reason |
|------|---------|---------------------------|--------|
| `2024-12-29` | Sun | `W52` | Last Sunday of ISO year 2024 (verified `(2024, 52, 7)`). |
| `2024-12-30` | Mon | `W01` | First day of ISO year 2025 (verified `(2025, 1, 1)`). |
| `2025-12-29` | Mon | `W01` | First day of ISO year 2026 (verified `(2026, 1, 1)`). |
| `2025-12-31` | Wed | `W01` | Confirms ISO year 2026 across calendar boundary. |
| `2026-01-01` | Thu | `W01` | Calendar New Year. |
| `2020-12-31` | Thu | `W53` | Year that contains 53 ISO weeks. |

All six rows verified by `qa-reviewer` against `date.isocalendar()` during phase-2 review.

#### B. Task-card multi-week fixtures for TC-026

| `start_date` | `end_date` | Expected chip text |
|--------------|------------|--------------------|
| `2026-04-27` | `2026-04-29` | `W18` |
| `2026-04-27` | `2026-05-04` | `W18–W19` |
| `2026-04-27` | `None`       | `W18` |
| `2026-05-04` | `2026-04-27` | `W19` (start-only; end-before-start is treated as no-end) |
| `None`       | `2026-04-29` | (no chip) |

#### C. Test-fixture conventions

- **TC-015 / TC-017 use `_resolve_peer_roots(file_value)` directly.** The function accepts a Python list-of-dicts as the first argument; tests pass a constructed list and `monkeypatch.setenv("PROJSTATUS_PEER_ROOTS", "")`. No `tmp_path/config.toml` plumbing required.
- **TC-020 symlink fixture.** Uses `os.symlink` to construct an escape path. On Windows, `os.symlink` requires Developer Mode enabled or the `SeCreateSymbolicLinkPrivilege`. The TC body checks symlink-creation privilege at the start and calls `pytest.skip("symlink privilege unavailable")` when missing — Windows CI without Developer Mode is acceptable, the canonicalization logic is still covered by the `..`-segment portion of the same TC.
- **Per-TC self-contained fixtures.** Every TC creates its own filesystem fixture under `tmp_path` (and its own env via `monkeypatch.setenv`) and does not depend on prior-TC state. Cross-TC dependencies are forbidden.

### 5.3 Batch acceptance criteria
- 100% of LLRs covered by at least one Test Case (TC) with `pass` result.
- 0 blocker fails in validation.
- Every HLR and LLR has an assigned validation method.
- `grep` of `should` inside any line whose first token is `HLR-NNN` or `LLR-NNN.M` returns zero matches.
- The locked design decisions in §6.2 each map to either an HLR or an explicit assumption in §2.5.
- **Per-TC self-contained fixtures.** Every TC creates its own filesystem fixture under `tmp_path` and its own environment via `monkeypatch.setenv`; no TC depends on prior-TC state.
- **Method distribution adds up.** The sum of TCs per method in §5.2 equals the total HLR + LLR count (currently 19 unit + 18 integration + 1 inspection = 38 = 14 HLR + 24 LLR).

---

## 6. Appendices

### 6.1 Extended glossary
*(See §1.3.)*

### 6.2 Relevant design decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| D-001 | Peer-root write enable is a per-peer `writable` flag in `config.toml` (default `false`). No runtime UI in this batch. | Smaller blast radius; cannot be flipped accidentally from the browser. Symmetric with the rest of the per-machine settings model. |
| D-002 | The Settings page is **non-mutating** this batch (display-only — reachability is computed per request via `Path.is_dir()` + `os.path.realpath` containment, so the rendered HTML may differ between renders). Editing `data_root` from the UI is deferred to a future batch. | Editing `data_root` requires a restart and validation logic that is not justified for this batch. "Non-mutating" is preferred over "read-only" because per-request reachability is technically a filesystem read, not an idempotent constant. |
| D-003 | Calendar-week numbering uses ISO 8601 (Monday-start, `W01`–`W53`). | Matches Python `date.isocalendar()`; standard in LATAM/EU business contexts. A configurable scheme is deferred to a future batch (US not raised). |
| D-004 | The Gantt `axisFormat` change MUST keep `import_timeline`'s round-trip stable; week tokens MUST appear only in the axis label, never in the per-task line tokens parsed by `mermaid.py`. | Preserve `sync_state.timeline_is_app_owned` semantics. |
| D-005 | When writing into a writable peer root, the recorded `actor` is the LOCAL operator, not the peer's owner. | Reflects who actually performed the change; the peer's own inbox attribution becomes correct when they configure us as a peer root. |

### 6.3 Open risks

| ID | Risk | Mitigation |
|----|------|------------|
| R-001 | A writable peer that is on a synced drive (OneDrive/Dropbox) may be mid-sync when ProjStatus writes to it, producing a sync conflict file. | Out of scope this batch; document in USER_GUIDE.md as a known limitation. |
| R-002 | An operator could accidentally mark a peer writable in `config.toml` without realizing it grants full write access. | Default value `false`; surface the writable state on the new Settings page so the operator can audit at a glance. |
| R-003 | ISO-week display on a task whose `start_date` and `end_date` fall in DIFFERENT ISO weeks is ambiguous. | **Resolved (architect, phase 1):** show `Wnn` alone when same ISO week, `Wnn–Wmm` when they differ. Edge cases (no end, end before start) covered explicitly in HLR-007 / LLR-007.1 after phase-2 review. |
| R-004 | Tests in `tests/test_mermaid_labels.py` will need updating when `axisFormat` changes. Failing to update them is a phase-3 risk, not a phase-1 one. | Listed explicitly in §5.2 (TC-009, TC-014, TC-029, TC-030, TC-038) and §5.3 batch acceptance criteria. |
| R-005 | Mermaid's `axisFormat` directive may not natively support a literal `W` prefix (`%V` token) on every renderer version pinned by `app/templates/base.html` CDN. | **Bound to HLR-014 / LLR-014.1** after phase-2 review. The fallback path is now a binding requirement (not implementer's choice). Implementer documents the chosen alternative in the increment review packet. |
| R-006 | Settings page "reachable" indicator now uses `Path.is_dir()` + `os.path.realpath` containment (LLR-010.1) rather than the original `Path.exists()`. A peer path that exists but is unreadable (permission-denied at runtime) may still display reachable=true. | Reduced via the `is_dir()` switch; full read-probe deferred to a future batch. |
| R-007 | HTML-substring assertions in `TestClient` confirm chip text is present in the DOM but not that it is visually rendered (CSS could hide it). | Mitigation: phase 4 includes a manual UAT checklist row per visual TC. A Playwright smoke test is out of scope for this batch (no harness in repo). |
| R-008 | Mermaid is loaded from a CDN by `app/templates/base.html` — pre-existing supply-chain dependency. This batch's `axisFormat` change does not introduce a new CDN entry but does not address the existing one either. | Acknowledged in A-011; mitigation deferred to a future security batch. |
| R-009 | Two human operators sharing one OS account (and therefore one `os.getlogin()` value) cannot be distinguished by `actor`. Addendums attribute both to the same string. | Acknowledged in A-009; out of scope for this batch. Surface a recommendation in phase-5 retrospective so future user stories don't silently rely on per-human attribution. |
| R-010 | Future user stories may add a configurable week scheme (Sunday-start, locale-driven, etc.) without explicit guard from D-003. The current LLRs hard-code ISO 8601. | Surface in phase-5 retrospective: any future `week_scheme` knob requires an HLR explicitly extending HLR-006. |
| R-011 | HLR-012 / LLR-012.1 use a block-list of dangerous paths. A future operator could mark a writable peer at a path not on the block list but still operationally sensitive (e.g., a CI runner workspace, a service account home dir on a shared box). | Future hardening: switch to an allow-list of explicitly safe locations (`Path.home()/Documents`, `Path.home()/Desktop`, `/mnt`, `/media`, an OneDrive/Dropbox subtree). Out of scope this batch — block-list is the cheaper edit and N-S-002 is closed by it. |
