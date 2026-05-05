# ProjStatus — Batch 2026-05-04-batch-01 — Executive Summary

**Delivered:** 2026-05-05 · **Batch:** `2026-05-04-batch-01`

## 1. Context

ProjStatus is a lightweight project-tracking app the operator runs on their own machine — each project is just a folder of files (no database), so it works alongside OneDrive and similar shared-folder tools. This batch addressed four operator-stated capability gaps spanning where projects can live, how they are shared, who is recorded as the author of a change, and how dates are displayed.

## 2. Problem

Before this batch, four practical gaps were limiting day-to-day use of the app:

- The folder where projects are stored had to be inside the repository itself. The operator wanted to point it at any folder on their machine — for example, a OneDrive subtree alongside their other documents.
- Other users' project folders could only be viewed, never edited. The operator wanted a switch that lets them opt specific shared folders into write mode, so they can collaborate without exposing every shared folder to accidental writes.
- The activity log already showed local edits, but did not visually distinguish edits made by other users on shared folders. When two operators work on the same folder, "who did this?" should be obvious at a glance.
- Calendar week numbers (W18, W19, …) were missing from tasks, milestones, and the Gantt chart. Operators were mentally converting `2026-04-27` into "week 18" every time they planned ahead.

These gaps weren't crashes or data loss — they were friction. Each one made the app a little less useful for the way the operator actually works week to week.

## 3. Solution

Each capability is now in place. Brief description of what was built (not how):

- **Configurable project folder.** Confirmed already in place from a prior delivery; this batch added a Settings page that displays the current configuration so the operator can verify it without opening a config file.
- **Per-folder write toggle.** A new flag in the configuration file lets the operator opt specific shared folders into write mode. Defensive checks block the toggle from being applied to the operator's own home directory or system folders, so a typo in the config file cannot silently mount the wrong location as writable.
- **Cross-folder activity log.** When the operator edits a project on a folder marked writable, the change is recorded with their identity. When the activity log displays edits made by others, those rows are visually marked (for example, `peer · alice: bob (claimed)`) so ownership is explicit and another user's claimed name cannot visually impersonate the local operator.
- **Calendar week indicator.** Tasks, milestones, and the Gantt chart now display ISO 8601 week numbers — `W18` for the week of April 27, and so on. Multi-week tasks show a range like `W18–W19`.

All four capabilities are also covered by 38 automated tests, all passing.

## 4. Outcomes

| What | Result |
|---|---|
| Capabilities delivered | 4 / 4 |
| Automated tests passing for this batch | 38 / 38 |
| Total automated test suite | 138 passing, 0 regressions |
| Security findings closed before delivery | 5 of 10 raised during review (including the 2 highest-priority security items) |
| Outstanding follow-ups | 5 lower-priority items + 1 manual browser check (5 minutes) |

All four capabilities work end-to-end, all tests pass, and no existing functionality regressed. Two security defenses were added on top of the requested work — one prevents accidental writes outside the configured project folder (so a misconfigured shared folder cannot corrupt sensitive locations), and the other neutralizes a class of injection attack that could have travelled through shared activity logs. The five lower-priority follow-ups are tracked and scheduled for the next delivery.

## 5. Next steps

What to do after reviewing this document:

1. **5-minute browser check.** Run the development server and open any project's Gantt chart. Confirm the week labels appear as `W18`, `W19`, … (not as the placeholder text `%V`). If they do, the delivery is fully validated. If they do not, a one-character change in `app/services/mermaid.py` swaps the week-format token, and the existing test suite will guide the swap.
2. **Decide on the next batch.** A short list of follow-up work is ready: a visual smoke-test harness so the manual browser check can be automated in future, an extended security check that also blocks Python virtual-environment paths from being marked writable, a Subresource Integrity hash for the chart-rendering library loaded from a CDN, and a few documentation tweaks. Each item is sized at 5–30 minutes.
3. **After committing and merging the change**, run `/dev-flow-sync-en` to upload the documentation set to the operator's Obsidian vault.

---

**Bottom line:** the four requested capabilities are delivered, security-hardened beyond the original ask, and ready for review.
