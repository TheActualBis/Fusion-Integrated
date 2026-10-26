from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from modules.leave import services
from modules.leave.models import (
    LeaveApprovalTask,
    LeaveAuthority,
    LeaveBalance,
    LeaveLedger,
    LeaveRequest,
    LeaveTransition,
    LeaveYearEndRun,
    LeaveType,
)
from modules.leave.views import _may_view_all_records

pytestmark = pytest.mark.django_db


def _request(*, category="CL", status="pending", request_kind="new", **values):
    leave_type, _ = LeaveType.objects.get_or_create(
        code=category,
        defaults={"name": category, "annual_entitlement": 8},
    )
    fields = {
        "employee_id": 10, "leave_type": leave_type,
        "start_date": date(2026, 11, 2), "end_date": date(2026, 11, 3),
        "days": 2, "reason": "Personal leave", "status": status,
        "request_kind": request_kind,
    }
    fields.update(values)
    return LeaveRequest.objects.create(**fields)


def test_replacement_substitute_reopens_only_the_consent_gate():
    row = _request(substitute_status="declined", substitute_id=20)
    LeaveApprovalTask.objects.create(
        leave_request=row, action="substitute_response", authority_role="substitute",
        assigned_user_id=20, status="completed", decision="decline", assigned_at=timezone.now(),
    )
    directory_rows = {
        10: SimpleNamespace(kind="staff"),
        30: SimpleNamespace(kind="faculty"),
    }
    with patch("modules.leave.services.directory.get_users", return_value=directory_rows):
        result = services.replace_substitute(
            request_id=row.pk, employee_id=10, substitute_id=30, actor_id=10,
        )

    result.refresh_from_db()
    task = result.tasks.get(status="pending")
    assert result.status == "pending"
    assert result.substitute_id == 30
    assert result.substitute_status == "pending"
    assert task.assigned_user_id == 30
    assert task.action == "substitute_response"


def test_higher_sanction_route_requires_unit_head_and_final_authority():
    row = _request(category="EL")
    LeaveAuthority.objects.create(category="EL", step_order=1, authority_role="Registrar")
    with pytest.raises(services.LeaveError, match="begin with the applicant's Unit Head"):
        services.route_for(row)


def test_resumption_uses_the_effective_period_after_an_approved_extension():
    today = timezone.localdate()
    root = _request(
        category="EL", status="approved", start_date=today - timedelta(days=10),
        end_date=today - timedelta(days=6), days=5,
    )
    extension = LeaveRequest.objects.create(
        employee_id=10, leave_type=root.leave_type, parent_request=root,
        request_kind="extension", start_date=today - timedelta(days=5),
        end_date=today - timedelta(days=2), days=4, reason="Approved extension",
        status="extended",
    )
    LeaveAuthority.objects.create(category="EL", step_order=1, authority_role="unit_head")
    LeaveAuthority.objects.create(category="EL", step_order=2, authority_role="Registrar")

    result = services.submit_related_request(
        parent_id=extension.pk, employee_id=10, actor_id=10, kind="resumption",
        start=date.min, end=date.min, reason="Returned to duty", actual_return_date=today,
    )

    assert result.parent_request_id == root.pk
    assert result.start_date == root.start_date
    assert result.end_date == extension.end_date
    assert result.days == root.days + extension.days


def test_on_time_resumption_after_extension_does_not_charge_leave_twice():
    today = timezone.localdate()
    leave_type, _ = LeaveType.objects.get_or_create(
        code="EL", defaults={"name": "Earned Leave", "annual_entitlement": 30}
    )
    root = LeaveRequest.objects.create(
        employee_id=10, leave_type=leave_type, start_date=today - timedelta(days=10),
        end_date=today - timedelta(days=6), days=5, reason="Approved leave",
        status="approved", balance_posted_at=timezone.now(),
    )
    extension = LeaveRequest.objects.create(
        employee_id=10, leave_type=leave_type, parent_request=root,
        request_kind="extension", start_date=today - timedelta(days=5),
        end_date=today - timedelta(days=1), days=5, reason="Approved extension",
        status="extended", balance_posted_at=timezone.now(),
    )
    balance = LeaveBalance.objects.create(
        employee_id=10, leave_type=leave_type, year=today.year,
        accrued=30, consumed=10,
    )
    resumption = LeaveRequest.objects.create(
        employee_id=10, leave_type=leave_type, parent_request=root,
        request_kind="resumption", start_date=root.start_date, end_date=extension.end_date,
        days=10, reason="Returned to duty", status="resumption_pending",
        actual_return_date=today,
    )
    task = LeaveApprovalTask.objects.create(
        leave_request=resumption, action="resumption_review", authority_role="Registrar",
        assigned_user_id=99, status="pending", assigned_at=timezone.now(),
    )

    services.respond_to_task(task_id=task.pk, actor_id=99, action="approve")

    balance.refresh_from_db()
    assert balance.consumed == 10
    assert not LeaveLedger.objects.filter(
        reference=f"resumption:{resumption.pk}", kind="resumption_adjustment",
    ).exists()


def test_sla_escalation_keeps_unassigned_tasks_actionable_and_logs_thresholds():
    row = _request()
    now = timezone.now()
    task = LeaveApprovalTask.objects.create(
        leave_request=row, action="sanction", authority_role="unit_head",
        assigned_user_id=11, assigned_at=now - timedelta(days=4),
        reminder_at=now - timedelta(days=3), escalation_at=now - timedelta(days=1),
    )

    result = services.process_sla(now=now)

    task.refresh_from_db()
    assert result == {"reminded": 1, "escalated": 1}
    assert task.status == "pending"
    assert task.reminder_sent_at is not None
    assert task.escalated_at is not None
    assert set(row.transitions.values_list("action", flat=True)) == {"sla_reminder", "sla_escalation"}


def test_approver_permission_does_not_grant_global_record_visibility():
    approver = SimpleNamespace(has_permission=lambda code: code == "leave.request.view")
    administrator = SimpleNamespace(has_permission=lambda code: code == "leave.configuration.manage")
    assert not _may_view_all_records(approver)
    assert _may_view_all_records(administrator)


def test_year_end_processing_cannot_lapse_the_current_year_early():
    with pytest.raises(services.LeaveError, match="only after that calendar year has ended"):
        services.process_year_end(timezone.localdate().year)


def test_year_end_retry_only_processes_unfinished_accounts():
    year = timezone.localdate().year - 1
    leave_type, _ = LeaveType.objects.get_or_create(
        code="EL", defaults={"name": "Earned Leave"}
    )
    first = services.LeaveBalance.objects.create(
        employee_id=21, leave_type=leave_type, year=year, opening=5,
    )
    second = services.LeaveBalance.objects.create(
        employee_id=22, leave_type=leave_type, year=year, opening=7,
    )
    original = services._process_year_end_balance

    def fail_second(balance, target_year, actor_id):
        if balance.employee_id == 22:
            raise services.LeaveError("temporary account failure")
        return original(balance, target_year, actor_id)

    with patch("modules.leave.services._process_year_end_balance", side_effect=fail_second):
        failed_run = services.process_year_end(year)
    first_key = f"{first.employee_id}:{first.leave_type_id}"
    second_key = f"{second.employee_id}:{second.leave_type_id}"
    assert failed_run.completed_at is None
    assert failed_run.processed_accounts == [first_key]
    assert len(failed_run.exceptions) == 1

    retried_run = services.process_year_end(year)
    assert retried_run.completed_at is not None
    assert retried_run.exceptions == []
    assert set(retried_run.processed_accounts) == {first_key, second_key}
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.available == 5
    assert second.available == 7
