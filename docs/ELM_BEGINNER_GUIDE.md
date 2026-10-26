# ELM beginner guide

This note is a quick map for someone opening the Employee Leave Management (ELM) code for the first time. The working module is `modules/leave`. The original Phase-1 `modules/elm` source has been copied unchanged to `phase1-preserved/modules/elm`. The current integrated employee leave workflows are in `modules/leave`, which uses Fusion navigation, identity, and permissions.

## Follow one request

1. The React screen is `client/src/modules/leave/pages/LeavePage.tsx`. It collects dates and sends the request through the hooks in `client/src/modules/leave/api.ts`.
2. The URL list is in `modules/leave/api/urls.py`. The view in `modules/leave/views.py` checks the caller's Fusion permissions and validates the incoming fields.
3. The workflow and database writes live in `modules/leave/services.py`. This is where a request is checked, assigned to the next reviewer, approved, or posted to a balance.
4. The small rules that do not need a database are in `modules/leave/domain.py`. For example, it calculates chargeable days, detects overlapping dates, and works out year-end carry-forward.
5. Tables and relationships are in `modules/leave/models.py`; schema changes are kept in `modules/leave/migrations/`.

## A few words in plain English

- **Permission check:** The backend asks Fusion whether the signed-in person may perform an action. Hiding a button in the browser is only a convenience; the backend check is what protects the data.
- **Approval task:** One action waiting for a specific role or person, such as substitute consent or Unit Head review. Finishing one task can create the next task.
- **Reservation:** Days held for a pending request. They are included when checking a new request so multiple pending requests cannot overbook the same balance.
- **Ledger:** A history of balance changes. It helps explain why a person's available balance changed.
- **Transaction:** A group of database changes that succeed together or are rolled back together if something fails.

## Where to start when reviewing a change

For a leave-rule change, read `domain.py` first, then find the service that calls it and the matching test. For a workflow change, follow the view into the service and inspect the approval-task tests. For an access change, check the permission on the view and confirm that the service scopes records to the employee or assigned reviewer.

The project-level review and known environment limitations are recorded in `docs/ELM_PHASE2_REVIEW.md`.
