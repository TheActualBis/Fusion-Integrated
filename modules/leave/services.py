"""Transactional ELM workflows and leave-account posting."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from modules.directory import contracts as directory
from modules.leave.domain import (
    CONTINUOUS_CATEGORIES,
    LEAVE_CATEGORIES,
    overlaps,
    requested_days,
    resumption_outcome,
    validate_extension,
    vacation_conversion,
    year_end_entitlement,
)
from modules.leave.models import (
    LeaveApprovalTask,
    LeaveAuthority,
    LeaveBalance,
    LeaveCalendar,
    LeaveCalendarDate,
    LeaveLedger,
    LeaveRequest,
    LeaveTransition,
    LeaveType,
    LeaveVacationPeriod,
    LeaveWorkflowConfig,
    LeaveYearEndRun,
)


class LeaveError(ValueError):
    """A leave rule or lifecycle guard rejected an action."""


def _role_key(value: str) -> str:
    return "_".join(value.strip().casefold().replace("(", " ").replace(")", " ").split())


def current_calendar(year: int) -> LeaveCalendar | None:
    return LeaveCalendar.objects.filter(year=year, status="published").first()


def closed_dates(start: date, end: date) -> set[date]:
    calendar = current_calendar(start.year)
    if not calendar:
        return set()
    return set(calendar.dates.filter(kind="holiday", date__range=(start, end)).values_list("date", flat=True))


def balance_for(employee_id: int, leave_type: LeaveType, year: int, *, create: bool = True) -> LeaveBalance | None:
    balance = LeaveBalance.objects.filter(employee_id=employee_id, leave_type=leave_type, year=year).first()
    if balance or not create:
        return balance
    balance, created = LeaveBalance.objects.get_or_create(
        employee_id=employee_id, leave_type=leave_type, year=year,
        defaults={"accrued": leave_type.annual_entitlement},
    )
    if created and leave_type.annual_entitlement:
        LeaveLedger.objects.create(
            employee_id=employee_id, leave_type=leave_type, year=year,
            amount=leave_type.annual_entitlement, kind="accrual",
            reference="annual-entitlement", note="Annual leave entitlement",
        )
    return balance


def _reserved_days(employee_id: int, leave_type_id: int, year: int, *, exclude_id: int | None = None) -> Decimal:
    pending = LeaveRequest.objects.filter(
        employee_id=employee_id, leave_type_id=leave_type_id, start_date__year=year,
        status__in=("pending", "extension_pending"), request_kind__in=("new", "extension"),
    )
    if exclude_id is not None:
        pending = pending.exclude(pk=exclude_id)
    return pending.aggregate(total=Sum("days"))["total"] or Decimal("0")


def _transition(row: LeaveRequest, actor_id: int | None, action: str, note: str = "",
                from_status: str | None = None) -> None:
    LeaveTransition.objects.create(
        leave_request=row, from_status=from_status or row.status, to_status=row.status,
        actor_id=actor_id, action=action, note=note[:500],
    )


def _config() -> LeaveWorkflowConfig:
    return LeaveWorkflowConfig.objects.order_by("pk").first() or LeaveWorkflowConfig.objects.create()


def _create_task(row: LeaveRequest, action: str, role: str, user_id: int | None = None) -> LeaveApprovalTask:
    cfg = _config()
    now = timezone.now()
    return LeaveApprovalTask.objects.create(
        leave_request=row, action=action, authority_role=role,
        assigned_user_id=user_id, assigned_at=now,
        reminder_at=now + timedelta(hours=cfg.reminder_hours),
        escalation_at=now + timedelta(hours=cfg.escalation_hours),
    )


def route_for(row: LeaveRequest) -> list[LeaveAuthority]:
    routes = list(LeaveAuthority.objects.filter(
        is_active=True, category=row.leave_type.code.upper(),
    ).filter(Q(unit_name=row.unit_name) | Q(unit_name="")).order_by("step_order"))
    # Prefer a route set up for the employee unit. Use the shared route
    # only when there is no unit-specific setup.
    specific = [step for step in routes if step.unit_name == row.unit_name]
    if specific:
        routes = specific
    if row.leave_type.code.upper() in {"CL", "RH"}:
        routes = [step for step in routes if _role_key(step.authority_role) == "unit_head"][:1]
        if not routes:
            raise LeaveError("Configure the applicant's Unit Head for this leave category and unit.")
    else:
        routes = [step for step in routes if not step.optional_step or _config().establishment_step_enabled]
        if not routes or _role_key(routes[0].authority_role) != "unit_head":
            raise LeaveError("Higher-sanction routes must begin with the applicant's Unit Head.")
        if routes[-1].is_establishment or _role_key(routes[-1].authority_role) == "unit_head":
            raise LeaveError("Configure a final Sanctioning Authority after the Unit Head review.")
    return routes


def _assign_next(row: LeaveRequest, actor_id: int | None = None) -> LeaveApprovalTask:
    if row.director_self_sanction and row.request_kind == "new":
        return _create_task(row, "sanction", "Director", row.employee_id)
    route = route_for(row)
    completed_steps = row.tasks.filter(status="completed", action__in=(
        "unit_head_review", "establishment_review", "sanction", "cancellation_decision", "extension_decision",
    )).count()
    if row.request_kind == "cancellation":
        action_final = "cancellation_decision"
    elif row.request_kind == "extension":
        action_final = "extension_decision"
    elif row.request_kind == "resumption":
        action_final = "resumption_review"
        if not route:
            raise LeaveError("Configure a sanctioning authority before submitting a resumption.")
        authority = route[-1]
        return _create_task(row, action_final, authority.authority_role, authority.assigned_user_id)
    else:
        action_final = "sanction"

    if not route:
        raise LeaveError("Configure an approval route for this leave category and unit first.")
    if completed_steps >= len(route):
        authority = route[-1]
        return _create_task(row, action_final, authority.authority_role, authority.assigned_user_id)
    authority = route[completed_steps]
    if authority.is_establishment:
        action = "establishment_review"
    elif _role_key(authority.authority_role) == "unit_head" and row.leave_type.code.upper() not in {"CL", "RH"}:
        action = "unit_head_review"
    else:
        action = action_final
    return _create_task(row, action, authority.authority_role, authority.assigned_user_id)


def _active_overlap(employee_id: int, start: date, end: date, half_day: str = "") -> LeaveRequest | None:
    rows = LeaveRequest.objects.filter(
        employee_id=employee_id,
        status__in=("pending", "approved", "extended", "cancellation_pending", "extension_pending"),
        start_date__lte=end, end_date__gte=start,
    )
    for row in rows:
        if overlaps(start, end, row.start_date, row.end_date, half_day=half_day, other_half_day=row.half_day):
            return row
    return None


def _validate_applicant(*, employee_id: int, leave_type: LeaveType, start: date, end: date,
                        half_day: str, substitute_id: int | None) -> tuple[Decimal, str]:
    people = directory.get_users([employee_id, substitute_id] if substitute_id else [employee_id])
    employee = people.get(employee_id)
    if not employee or employee.kind not in {"faculty", "staff"}:
        raise LeaveError("Only active faculty and staff can apply for leave.")
    category = leave_type.code.upper()
    if category not in LEAVE_CATEGORIES:
        raise LeaveError("This leave category is outside the ELM policy.")
    if leave_type.eligible_kinds and employee.kind not in leave_type.eligible_kinds:
        raise LeaveError("This leave category is not available to your employee group.")
    if start.year != end.year:
        raise LeaveError("Submit a separate request for each calendar year.")
    cal = current_calendar(start.year)
    holidays = closed_dates(start, end)
    days = requested_days(start, end, holidays, category=category, half_day=half_day)
    if category == "RH":
        if start != end or not cal or not cal.dates.filter(date=start, kind="restricted").exists():
            raise LeaveError("Choose one Restricted Holiday from the currently published calendar.")
    if category == "VL" and not LeaveVacationPeriod.objects.filter(
        start_date__lte=start, end_date__gte=end,
    ).exists():
        raise LeaveError("Vacation Leave must fall within an Academic Calendar vacation period.")
    if _active_overlap(employee_id, start, end, half_day):
        raise LeaveError("This period overlaps another pending or approved leave request.")
    if substitute_id is not None:
        substitute = people.get(substitute_id)
        if substitute_id == employee_id or not substitute or substitute.kind not in {"faculty", "staff"}:
            raise LeaveError("The substitute must be another active employee.")
        if _active_overlap(substitute_id, start, end):
            raise LeaveError("The nominated substitute has overlapping leave.")
    return days, employee.department


@transaction.atomic
def submit_request(*, employee_id: int, leave_type_id: int, start: date, end: date, reason: str,
                   actor_id: int, half_day: str = "", station_leave: bool = False,
                   station_leave_details: str = "", substitute_id: int | None = None,
                   document_url: str = "", director_self_sanction: bool = False) -> LeaveRequest:
    leave_type = LeaveType.objects.select_for_update().filter(pk=leave_type_id, is_active=True).first()
    if not leave_type:
        raise LeaveError("Choose an active ELM leave category.")
    if not reason.strip():
        raise LeaveError("Enter a reason for the leave request.")
    if station_leave and not station_leave_details.strip():
        raise LeaveError("Add the Station Leave details to this application.")
    if leave_type.requires_document and not document_url:
        raise LeaveError("Supporting medical evidence is required for this category.")
    days, department = _validate_applicant(
        employee_id=employee_id, leave_type=leave_type, start=start, end=end,
        half_day=half_day, substitute_id=substitute_id,
    )
    balance = balance_for(employee_id, leave_type, start.year)
    if balance:
        balance = LeaveBalance.objects.select_for_update().get(pk=balance.pk)
    # Pending requests reserve days too, so two requests cannot spend the
    # same balance while they wait for approval.
    reserved = _reserved_days(employee_id, leave_type.pk, start.year)
    if leave_type.code.upper() == "SCL":
        used = balance.consumed if balance else Decimal("0")
        if used + reserved + days > leave_type.annual_entitlement:
            raise LeaveError("Special Casual Leave cannot exceed its annual entitlement.")
    if not balance or balance.available - reserved < days:
        available = balance.available if balance else Decimal("0")
        raise LeaveError(f"Insufficient balance after pending requests. You have {max(available - reserved, Decimal('0'))} day(s) available.")
    row = LeaveRequest.objects.create(
        employee_id=employee_id, leave_type=leave_type, start_date=start, end_date=end,
        days=days, reason=reason.strip(), document_url=document_url, half_day=half_day,
        station_leave=station_leave, station_leave_details=station_leave_details.strip(),
        substitute_id=substitute_id, substitute_status="pending" if substitute_id else "",
        unit_name=department,
        workflow_stage="substitute" if substitute_id else "approval",
        director_self_sanction=director_self_sanction,
    )
    LeaveTransition.objects.create(leave_request=row, to_status=row.status, actor_id=actor_id, action="submitted")
    if substitute_id:
        _create_task(row, "substitute_response", "substitute", substitute_id)
    else:
        _assign_next(row, actor_id)
    return row


@transaction.atomic
def replace_substitute(*, request_id: int, employee_id: int, substitute_id: int,
                       actor_id: int) -> LeaveRequest:
    """Replace a declined substitute once while the request is still pending."""
    row = LeaveRequest.objects.select_for_update().select_related("leave_type").filter(
        pk=request_id, employee_id=employee_id,
        request_kind__in=("new", "extension"), status__in=("pending", "extension_pending"),
        substitute_status="declined",
    ).first()
    if not row:
        raise LeaveError("A pending request with a declined substitute was not found.")
    declines = row.tasks.filter(action="substitute_response", decision="decline").count()
    if declines != 1:
        raise LeaveError("Only one replacement substitute is allowed after a decline.")
    people = directory.get_users([employee_id, substitute_id])
    applicant = people.get(employee_id)
    substitute = people.get(substitute_id)
    if (substitute_id == employee_id or not applicant or not substitute
            or applicant.kind not in {"faculty", "staff"}
            or substitute.kind not in {"faculty", "staff"}):
        raise LeaveError("The replacement must be another active employee.")
    if _active_overlap(substitute_id, row.start_date, row.end_date):
        raise LeaveError("The replacement substitute has overlapping leave.")
    if row.tasks.filter(status="pending").exists():
        raise LeaveError("A substitute response is already pending.")
    row.substitute_id = substitute_id
    row.substitute_status = "pending"
    row.workflow_stage = "substitute"
    row.save(update_fields=["substitute_id", "substitute_status", "workflow_stage", "updated_at"])
    _create_task(row, "substitute_response", "substitute", substitute_id)
    _transition(row, actor_id, "replacement_substitute_nominated")
    return row


def _post_consumption(row: LeaveRequest, actor_id: int, days: Decimal | None = None) -> None:
    amount = days if days is not None else row.days
    balance = LeaveBalance.objects.select_for_update().filter(
        employee_id=row.employee_id, leave_type=row.leave_type, year=row.start_date.year,
    ).first()
    reserved = _reserved_days(row.employee_id, row.leave_type_id, row.start_date.year, exclude_id=row.pk)
    if not balance or balance.available - reserved < amount:
        raise LeaveError("The employee no longer has enough balance for this leave.")
    # Save the balance change and ledger entry together in this transaction.
    balance.consumed += amount
    balance.save(update_fields=["consumed", "updated_at"])
    LeaveLedger.objects.create(
        employee_id=row.employee_id, leave_type=row.leave_type, year=row.start_date.year,
        amount=-amount, kind="consumption", reference=f"request:{row.pk}",
        actor_id=actor_id, note="Approved leave",
    )
    row.balance_posted_at = timezone.now()


def _restore_consumption(row: LeaveRequest, actor_id: int) -> None:
    if not row.balance_posted_at:
        return
    balance = LeaveBalance.objects.select_for_update().get(
        employee_id=row.employee_id, leave_type=row.leave_type, year=row.start_date.year,
    )
    balance.consumed = max(Decimal("0"), balance.consumed - row.days)
    balance.save(update_fields=["consumed", "updated_at"])
    LeaveLedger.objects.create(
        employee_id=row.employee_id, leave_type=row.leave_type, year=row.start_date.year,
        amount=row.days, kind="restoration", reference=f"cancellation:{row.pk}",
        actor_id=actor_id, note="Approved leave cancellation",
    )
    row.balance_posted_at = None


def _finish_task(task: LeaveApprovalTask, decision: str, note: str) -> None:
    task.status = "completed"
    task.decision = decision
    task.note = note[:500]
    task.save(update_fields=["status", "decision", "note", "updated_at"])


@transaction.atomic
def respond_to_task(*, task_id: int, actor_id: int, action: str, note: str = "") -> LeaveRequest:
    task = LeaveApprovalTask.objects.select_for_update().select_related("leave_request", "leave_request__leave_type").filter(
        pk=task_id, status="pending",
    ).first()
    if not task:
        raise LeaveError("This task is no longer pending.")
    row = LeaveRequest.objects.select_for_update().get(pk=task.leave_request_id)
    prior_status = row.status
    if task.assigned_user_id and task.assigned_user_id != actor_id:
        raise LeaveError("This task is assigned to another user.")
    if action not in {"accept", "decline", "recommend", "not_recommend", "verify", "approve", "reject"}:
        raise LeaveError("Choose a valid action for this task.")
    if action == "reject" and not note.strip():
        raise LeaveError("Add a reason when rejecting a request.")

    if task.action == "substitute_response":
        if action not in {"accept", "decline"}:
            raise LeaveError("A substitute can accept or decline the assignment.")
        row.substitute_status = "accepted" if action == "accept" else "declined"
        if action == "accept":
            _finish_task(task, action, note)
            row.workflow_stage = "approval"
            _assign_next(row, actor_id)
        else:
            _finish_task(task, action, note)
            row.workflow_stage = "replacement_substitute"
        row.save(update_fields=["substitute_status", "workflow_stage", "updated_at"])
        _transition(row, actor_id, action, note)
        return row

    if task.action == "unit_head_review":
        if action not in {"recommend", "not_recommend"}:
            raise LeaveError("The Unit Head records Recommended or Not Recommended here.")
        row.unit_head_recommendation = "recommended" if action == "recommend" else "not_recommended"
        _finish_task(task, action, note)
        row.save(update_fields=["unit_head_recommendation", "updated_at"])
        _assign_next(row, actor_id)
        _transition(row, actor_id, action, note)
        return row

    if task.action == "establishment_review":
        if action != "verify":
            raise LeaveError("The Establishment step records verification and routing.")
        _finish_task(task, action, note)
        _assign_next(row, actor_id)
        _transition(row, actor_id, action, note)
        return row

    final_actions = {"sanction", "cancellation_decision", "extension_decision", "resumption_review"}
    if task.action not in final_actions:
        raise LeaveError("This task does not accept a final decision.")
    if action not in {"approve", "reject"}:
        raise LeaveError("The Sanctioning Authority must approve or reject this request.")
    _finish_task(task, action, note)
    if action == "reject":
        row.status = "rejected"
    elif row.request_kind == "cancellation":
        row.status = "cancelled"
        original = LeaveRequest.objects.select_for_update().get(pk=row.parent_request_id)
        original.status = "cancelled"
        _restore_consumption(original, actor_id)
        original.save(update_fields=["status", "balance_posted_at", "updated_at"])
    elif row.request_kind == "extension":
        row.status = "extended"
        _post_consumption(row, actor_id)
    elif row.request_kind == "resumption":
        parent = LeaveRequest.objects.select_for_update().get(pk=row.parent_request_id)
        # `row` spans the root request and all approved extensions. Comparing
        # against the root end date would classify an on-time return after an
        # extension as late and charge the account a second time.
        outcome = resumption_outcome(row.end_date, row.actual_return_date)
        row.status = "approved"
        if outcome != "normal":
            last_leave_day = row.actual_return_date - timedelta(days=1)
            new_days = (requested_days(parent.start_date, last_leave_day, category=parent.leave_type.code)
                        if last_leave_day >= parent.start_date else Decimal("0"))
            delta = parent.days - new_days
            if delta > 0:
                balance = LeaveBalance.objects.select_for_update().get(employee_id=parent.employee_id, leave_type=parent.leave_type, year=parent.start_date.year)
                balance.consumed = max(Decimal("0"), balance.consumed - delta)
                balance.save(update_fields=["consumed", "updated_at"])
                LeaveLedger.objects.create(employee_id=parent.employee_id, leave_type=parent.leave_type, year=parent.start_date.year, amount=delta, kind="resumption_adjustment", reference=f"resumption:{row.pk}", actor_id=actor_id, note=f"{outcome.title()} resumption adjustment")
            elif delta < 0:
                _post_consumption(row, actor_id, -delta)
                LeaveLedger.objects.filter(reference=f"request:{row.pk}", kind="consumption").update(
                    reference=f"resumption:{row.pk}", note="Late resumption adjustment",
                )
    else:
        row.status = "approved"
        _post_consumption(row, actor_id)
    row.reviewer_id = actor_id
    row.reviewer_note = note.strip()[:500]
    row.decided_at = timezone.now()
    row.save()
    _transition(row, actor_id, action, note, from_status=prior_status)
    return row


@transaction.atomic
def withdraw_request(*, request_id: int, employee_id: int) -> LeaveRequest:
    row = LeaveRequest.objects.select_for_update().filter(pk=request_id, employee_id=employee_id).first()
    if not row or row.status not in {
        "pending", "cancellation_pending", "extension_pending", "resumption_pending",
    }:
        raise LeaveError("Only a pending request can be withdrawn.")
    old = row.status
    row.status = "withdrawn"
    row.save(update_fields=["status", "updated_at"])
    row.tasks.filter(status="pending").update(status="withdrawn")
    LeaveTransition.objects.create(leave_request=row, from_status=old, to_status="withdrawn", actor_id=employee_id, action="withdrawn")
    return row


@transaction.atomic
def submit_related_request(*, parent_id: int, employee_id: int, kind: str, actor_id: int,
                          start: date, end: date, reason: str, substitute_id: int | None = None,
                          actual_return_date: date | None = None, document_url: str = "") -> LeaveRequest:
    parent = LeaveRequest.objects.select_for_update().select_related("leave_type", "parent_request").filter(
        pk=parent_id, employee_id=employee_id, status__in=("approved", "extended"),
    ).first()
    if not parent:
        raise LeaveError("An approved leave record for you was not found.")
    category = parent.leave_type.code.upper()
    if kind == "cancellation":
        if parent.related_requests.filter(
            request_kind="cancellation", status="cancellation_pending",
        ).exists():
            raise LeaveError("A cancellation request is already awaiting a decision.")
        if parent.start_date <= timezone.localdate():
            raise LeaveError("Cancellation is available only before the approved leave begins.")
        days, details = parent.days, parent.unit_name
        status = "cancellation_pending"
    elif kind == "extension":
        today = timezone.localdate()
        if not parent.start_date <= today <= parent.end_date:
            raise LeaveError("An extension is available only while the approved leave is ongoing.")
        validate_extension(category=category, original_end=parent.end_date, new_end=end)
        start = parent.end_date + timedelta(days=1)
        days, details = _validate_applicant(employee_id=employee_id, leave_type=parent.leave_type,
            start=start, end=end, half_day="", substitute_id=substitute_id)
        if parent.leave_type.requires_document and not document_url:
            raise LeaveError("Supporting medical evidence is required for this extension.")
        balance = balance_for(employee_id, parent.leave_type, start.year)
        if balance:
            balance = LeaveBalance.objects.select_for_update().get(pk=balance.pk)
        reserved = _reserved_days(employee_id, parent.leave_type_id, start.year)
        if not balance or balance.available - reserved < days:
            raise LeaveError("The extension exceeds the available leave balance after pending requests.")
        status = "extension_pending"
    elif kind == "resumption":
        if category not in CONTINUOUS_CATEGORIES or not actual_return_date:
            raise LeaveError("Resumption is available for EL, COL, and VL and needs an actual return date.")
        if actual_return_date > timezone.localdate():
            raise LeaveError("The actual return date cannot be in the future.")
        root = parent
        while root.request_kind == "extension" and root.parent_request_id:
            root = LeaveRequest.objects.select_for_update().select_related("leave_type", "parent_request").get(
                pk=root.parent_request_id,
            )
        if actual_return_date < root.start_date:
            raise LeaveError("The resumption date cannot precede the approved leave period.")
        if root.related_requests.filter(
            request_kind="resumption", status__in=("resumption_pending", "approved"),
        ).exists():
            raise LeaveError("A resumption has already been submitted for this leave period.")
        extensions = []
        pending_parents = [root]
        while pending_parents:
            current = pending_parents.pop()
            children = list(current.related_requests.filter(request_kind="extension", status="extended"))
            extensions.extend(children)
            pending_parents.extend(children)
        parent = root
        start = root.start_date
        end = max([root.end_date, *(extension.end_date for extension in extensions)])
        days = root.days + sum((extension.days for extension in extensions), Decimal("0"))
        details = root.unit_name
        status = "resumption_pending"
    else:
        raise LeaveError("Choose cancellation, extension, or resumption.")
    row = LeaveRequest.objects.create(
        employee_id=employee_id, leave_type=parent.leave_type, parent_request=parent,
        request_kind=kind, start_date=start, end_date=end, days=days,
        reason=reason.strip(), document_url=document_url, substitute_id=substitute_id,
        substitute_status="pending" if substitute_id and kind == "extension" else "",
        unit_name=details, status=status, workflow_stage="substitute" if substitute_id else kind,
        actual_return_date=actual_return_date,
    )
    LeaveTransition.objects.create(leave_request=row, to_status=row.status, actor_id=actor_id, action=f"{kind}_submitted")
    if substitute_id and kind == "extension":
        _create_task(row, "substitute_response", "substitute", substitute_id)
    else:
        _assign_next(row, actor_id)
    return row


@transaction.atomic
def record_offline_leave(*, employee_id: int, leave_type_id: int, start: date, end: date,
                         reason: str, reference: str, evidence_url: str, actor_id: int) -> LeaveRequest:
    leave_type = LeaveType.objects.filter(pk=leave_type_id, is_active=True).first()
    if not leave_type or not reference.strip():
        raise LeaveError("Choose a leave category and enter the offline sanction reference.")
    if not evidence_url:
        raise LeaveError("Attach the sanction evidence URL.")
    days, department = _validate_applicant(employee_id=employee_id, leave_type=leave_type,
        start=start, end=end, half_day="", substitute_id=None)
    balance = balance_for(employee_id, leave_type, start.year)
    if not balance or balance.available < days:
        raise LeaveError("The offline entry exceeds the available balance.")
    row = LeaveRequest.objects.create(
        employee_id=employee_id, leave_type=leave_type, request_kind="offline",
        start_date=start, end_date=end, days=days, reason=reason.strip(),
        status="recorded_offline", unit_name=department,
        offline_reference=reference.strip(), offline_evidence_url=evidence_url,
        decided_at=timezone.now(), reviewer_id=actor_id,
    )
    _post_consumption(row, actor_id)
    row.save(update_fields=["balance_posted_at", "updated_at"])
    LeaveTransition.objects.create(leave_request=row, to_status=row.status, actor_id=actor_id, action="offline_recorded", note=reference[:500])
    return row


@transaction.atomic
def process_year_end(year: int, actor_id: int | None = None) -> LeaveYearEndRun:
    if year >= timezone.localdate().year:
        raise LeaveError("Year-end processing is available only after that calendar year has ended.")
    run, _created = LeaveYearEndRun.objects.get_or_create(year=year, defaults={"started_by": actor_id})
    run = LeaveYearEndRun.objects.select_for_update().get(pk=run.pk)
    if run.completed_at:
        return run
    exceptions: list[str] = []
    for balance in LeaveBalance.objects.select_for_update().filter(year=year).select_related("leave_type").order_by("pk"):
        category = balance.leave_type.code.upper()
        account_key = f"{balance.employee_id}:{balance.leave_type_id}"
        if account_key in run.processed_accounts:
            continue
        try:
            with transaction.atomic():
                _process_year_end_balance(balance, year, actor_id)
                LeaveYearEndRun.objects.filter(pk=run.pk).update(
                    processed_accounts=[*run.processed_accounts, account_key],
                    updated_at=timezone.now(),
                )
            run.processed_accounts.append(account_key)
        except Exception as exc:  # Keep processing other accounts; the run reports each failed account.
            exceptions.append(f"employee {balance.employee_id}, {category}: {exc}")
    run.exceptions = exceptions
    run.completed_at = timezone.now() if not exceptions else None
    run.save(update_fields=["exceptions", "completed_at", "updated_at"])
    return run


def _process_year_end_balance(balance: LeaveBalance, year: int, actor_id: int | None) -> None:
    category = balance.leave_type.code.upper()
    unused = max(balance.available, Decimal("0"))
    configured_limit = balance.leave_type.carry_forward_limit
    lapsed, carried = year_end_entitlement(
        category=category, unused=unused,
        carry_forward_limit=(configured_limit or None)
        if category in {"EL", "COL"} else configured_limit,
    )
    if category == "VL":
        carried = vacation_conversion(unused)
        lapsed = unused
        el_type = LeaveType.objects.filter(code__iexact="EL").first()
        if not el_type:
            raise LeaveError("Earned Leave category is missing; Vacation Leave conversion was not posted.")
        target = balance_for(balance.employee_id, el_type, year + 1)
        target.opening += carried
        target.save(update_fields=["opening", "updated_at"])
        LeaveLedger.objects.create(employee_id=balance.employee_id, leave_type=el_type, year=year + 1, amount=carried, kind="vl_conversion", reference=f"year-end:{year}", actor_id=actor_id, note="Unused Vacation Leave converted at 2:1")
    elif category in {"EL", "COL"}:
        target = balance_for(balance.employee_id, balance.leave_type, year + 1)
        target.opening += carried
        target.save(update_fields=["opening", "updated_at"])
        if carried:
            LeaveLedger.objects.create(employee_id=balance.employee_id, leave_type=balance.leave_type, year=year + 1, amount=carried, kind="carry_forward", reference=f"year-end:{year}", actor_id=actor_id, note="Year-end carry-forward")
    if lapsed:
        LeaveLedger.objects.create(employee_id=balance.employee_id, leave_type=balance.leave_type, year=year, amount=-lapsed, kind="lapse", reference=f"year-end:{year}", actor_id=actor_id, note="Unused leave lapsed at year end")
    if balance.leave_type.annual_entitlement and category != "VL":
        target = balance_for(balance.employee_id, balance.leave_type, year + 1)
        if target.accrued == 0:
            target.accrued = balance.leave_type.annual_entitlement
            target.save(update_fields=["accrued", "updated_at"])
            LeaveLedger.objects.create(employee_id=balance.employee_id, leave_type=balance.leave_type, year=year + 1, amount=balance.leave_type.annual_entitlement, kind="accrual", reference=f"annual-entitlement:{year + 1}", actor_id=actor_id, note="Annual leave entitlement")


@transaction.atomic
def process_sla(now=None) -> dict[str, int]:
    now = now or timezone.now()
    reminded = escalated = 0
    for task in LeaveApprovalTask.objects.select_for_update().filter(status="pending").select_related("leave_request"):
        if task.reminder_at and task.reminder_at <= now and not task.reminder_sent_at:
            task.reminder_sent_at = now
            reminded += 1
            _transition(task.leave_request, None, "sla_reminder", "Reminder threshold reached.")
        if task.escalation_at and task.escalation_at <= now and not task.escalated_at:
            task.escalated_at = now
            escalated += 1
            cfg = _config()
            authority = LeaveAuthority.objects.filter(
                is_active=True, category=task.leave_request.leave_type.code.upper(),
                authority_role=cfg.escalation_authority_role,
            ).filter(Q(unit_name=task.leave_request.unit_name) | Q(unit_name="")).order_by(
                "-unit_name", "step_order",
            ).first() if cfg.escalation_authority_role else None
            if authority:
                task.authority_role = authority.authority_role
                if authority.assigned_user_id:
                    task.assigned_user_id = authority.assigned_user_id
            _transition(
                task.leave_request, None, "sla_escalation",
                f"Escalated to {authority.authority_role}." if authority else "Escalation threshold reached; task remains pending.",
            )
        task.save(update_fields=["reminder_sent_at", "escalated_at", "status", "updated_at"])
        if task.assigned_user_id or task.authority_role:
            task.save(update_fields=["assigned_user_id", "authority_role", "updated_at"])
    return {"reminded": reminded, "escalated": escalated}
