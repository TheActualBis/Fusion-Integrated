# ELM Phase 2 Review and Improvement Record

Date: 2026-10-26

## Preservation

The selected Phase 1 implementation is preserved in
`phase1-preserved/modules/elm`. A SHA-256 comparison against the active
`modules/elm` source confirmed all preserved files match. The Phase 1 code
remains installed at `/api/v1/elm/` for separate evaluation. The Phase 2
implementation is a separate app at `/api/v1/leave/` with its own `leave.*`
permission namespace and client routes.

This workspace does not expose usable Git metadata or a Git executable, so a
Git status, branch, and Git diff could not be produced. The final file review
used SHA-256 comparisons against the preserved copy instead. There are no
deleted files.

## Specification material reviewed

The repository contains and the review used the Problem Statement v1.4,
Functional Requirement Specification v1.5, Use Case Specifications v1.4,
Business Rule Specifications v1.4, Traceability Matrix v1.5, and Workflow
Specifications v1.6. `ELM_ALL_SPECIFICATIONS.txt` is not present.

The package calls for employee leave applications and history, authority-based
review and sanction, substitute handling, leave categories and balances,
calendar rules, related requests such as cancellation/extension/resumption,
offline records, year-end processing, and administrative configuration. Where
the available Fusion interfaces do not supply an external system or a clear
rule, this implementation uses manual configuration or records the gap below.

## Defects addressed

- Restricted approval queue and ledger visibility so request-view permission
  alone does not expose other employees' records.
- Added one-time replacement of a declined substitute, with employee and
  overlapping-leave checks, API authorization, UI, and a focused test.
- Required a Unit Head at the start of higher-sanction routes and a final
  sanction authority after the review steps.
- Kept SLA-escalated approval tasks pending/actionable and recorded reminder
  and escalation transitions instead of leaving a task without an actionable
  recipient state.
- Counted extended leave as active for overlap checks and corrected resumption
  handling to use the root request and approved extensions.
- Prevented current/future calendar years from being processed early.
- Made year-end processing retryable after account failures. Successful
  employee/type accounts are recorded in the same transaction as their ledger
  postings; a retry skips completed accounts and processes failed ones. Added
  migration `0003_year_end_retry.py` and a regression test. A merge migration
  now joins the two `0003` branches so Django has one consistent migration
  graph.
- Corrected resumption classification to compare the actual return-to-duty
  date with the day after the effective approved leave end, including approved
  extensions. Added regression coverage against charging leave twice.
- Added configuration screens for calendars, vacation periods, approval
  authorities, SLA settings, and (when separately permitted) offline records.
- Added CSV export and a printable view of an employee's own request list.
- Hid balance adjustment controls unless the session has the corresponding
  permission; server authorization remains authoritative.

## Files changed or added

Changed:

- `client/src/modules/leave/api.ts`
- `client/src/modules/leave/pages/LeavePage.tsx`
- `modules/leave/models.py`
- `modules/leave/services.py`
- `modules/leave/views.py`
- `modules/leave/api/urls.py`
- `modules/leave/management/commands/process_leave_year_end.py`
- `modules/leave/tests/test_domain.py`
- `modules/leave/domain.py`

Added:

- `client/src/modules/leave/pages/LeaveAdminSettings.tsx`
- `modules/leave/migrations/0003_year_end_retry.py`
- `modules/leave/migrations/0005_merge_year_end_and_director.py`
- `modules/leave/tests/test_workflows.py`
- `docs/ELM_PHASE2_REVIEW.md`

No dependency files were changed. The frontend uses Fusion's existing
authentication/session permissions, shared API client, shell, and UI library.
The backend retains the existing IAM identity and permission checks.

## Verification performed

- `npm run typecheck`: passed after the frontend changes and during the latest
  review run.
- The Phase 1 and Phase 2 permission entries remain distinct (`elm.*` and
  `leave.*`); static inspection confirmed their API mounts and app labels are
  separate.
- `npm run build`: TypeScript compilation completed, then Vite failed while
  loading its configuration: esbuild reported `Cannot read directory "../../..":
  Access is denied` and could not resolve `vite.config.ts`.
- `npm run dev -- --host 127.0.0.1`: failed at the same Vite/esbuild config
  loading error; no frontend server started.
- `npm test`: Vitest could not load its config for the same esbuild access
  restriction. No frontend test cases ran.
- `npm run lint`: could not run because ESLint is not installed in the available
  `node_modules`.
- Django tests/checks and migration checks were not runnable. The `python`
  command resolves to a WindowsApps alias that cannot execute; `py`, `uv`,
  Docker, and Ruff are not available. Therefore the new backend regression test
  and migration have not been executed/applied. Explicit attempts to run
  `python manage.py check` and `python manage.py test modules.leave.tests` both
  failed before Django could start because `python.exe` could not be accessed.
- No application server or database was available for an ELM runtime/API
  integration check.
- The in-repository Phase 1 snapshot still matches `modules/elm` byte-for-byte.
  Git diff inspection was unavailable.

## Remaining gaps and limitations

- Backend behavior, database migration, authorization, persistence, and
  year-end retry behavior remain unverified at runtime until Python and the
  development database are available.
- SLA processing records thresholds and may reassign a task if an escalation
  authority is configured, but it does not deliver reminders or notifications.
  The existing notification worker is scoped to Placement topics; ELM has no
  configured notification delivery integration.
- Leave vacation periods are entered manually. They are not synchronized from
  an academic-calendar service. Attendance/resumption is also not integrated
  with an attendance system.
- Authority routing is configured by unit and role, with optional manual user
  assignment. Automatic designation-to-user resolution is not wired to an IAM
  directory interface in this implementation.
- Printing/export currently covers an employee's own request list (CSV and a
  print view), not a formatted individual application form or administrative
  report export.
- The specifications do not fully establish whether a substitute is
  mandatory in every case or define all cross-year leave behavior. The module
  does not add a new blanket substitute requirement; the existing service
  requires separate requests within a single calendar year.

## Setup still required

With the documented Python 3.12/Django environment and development database
available, install project dependencies, run Django checks and the test suite,
apply migrations, seed the leave module/permissions, and start the Fusion
application. Then exercise the specified workflows and authorization cases
against the running API. The migration in this phase is
`modules.leave.0005_merge_year_end_and_director`; migrations have not been
applied in this environment.
