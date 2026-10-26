from decimal import Decimal
import datetime

from django.db import transaction, IntegrityError
from django.db.models import Q, Sum
from django.utils import timezone

from modules.elm.domain import (
    half_days_overlap, leave_days, split_days_by_year, validate_balance, validate_rh_date,
    validate_scl, year_end_lapse)
from modules.elm.models import (
    LeaveApplication, LeaveBalance, LeaveTransaction, RestrictedHoliday, 
    LeaveApprovalTask, LeaveAuthority, LeaveWorkflowConfig, ANNUAL_ENTITLEMENT)

def _role_key(value: str) -> str:
    return "_".join(value.strip().casefold().replace("(", " ").replace(")", " ").split())

def _config() -> LeaveWorkflowConfig:
    return LeaveWorkflowConfig.objects.order_by("pk").first() or LeaveWorkflowConfig.objects.create()

def _create_task(application, action: str, role: str, user_id: int | None = None) -> LeaveApprovalTask:
    cfg = _config()
    now = timezone.now()
    return LeaveApprovalTask.objects.create(
        application=application, action=action, authority_role=role,
        assigned_user_id=user_id, assigned_at=now,
        reminder_at=now + datetime.timedelta(hours=cfg.reminder_hours),
        escalation_at=now + datetime.timedelta(hours=cfg.escalation_hours),
    )

def route_for(application) -> list[LeaveAuthority]:
    routes = list(LeaveAuthority.objects.filter(
        is_active=True, leave_type=application.leave_type,
    ).filter(Q(unit_name=application.user.department) | Q(unit_name="")).order_by("step_order"))
    
    specific = [step for step in routes if step.unit_name == application.user.department]
    if specific:
        routes = specific
        
    return routes

def _assign_next(application, actor_id: int | None = None) -> LeaveApprovalTask:
    route = route_for(application)
    completed_steps = application.approval_tasks.filter(status="COMPLETED").count()
    
    if not route:
        raise ValueError("No approval route configured for this leave type and unit.")
    
    if completed_steps >= len(route):
        # All defined steps done, assign final sanction to the last authority
        authority = route[-1]
        return _create_task(application, "sanction", authority.authority_role, authority.assigned_user_id)
    
    authority = route[completed_steps]
    action = "sanction" if completed_steps == len(route) - 1 else "review"
    return _create_task(application, action, authority.authority_role, authority.assigned_user_id)

def get_leave_summary(user, year=None):
    """
    Generates a comprehensive summary of a user's leave status for export.
    If year is None, it uses the current year.
    """
    import datetime
    target_year = year or datetime.date.today().year
    
    # 1. Get Balances
    balances = LeaveBalance.objects.filter(user=user, year=target_year)
    balance_data = [
        {
            "type": b.leave_type,
            "entitled": float(b.entitled),
            "used": float(b.used),
            "lapsed": float(b.lapsed),
            "available": float(b.entitled - b.used)
        }
        for b in balances
    ]
    
    # 2. Get Application History
    apps = LeaveApplication.objects.filter(
        user=user, 
        start_date__year=target_year
    ).order_by("-created_at")
    
    history = [
        {
            "id": a.id,
            "type": a.leave_type,
            "start": a.start_date.isoformat(),
            "end": a.end_date.isoformat(),
            "days": float(a.days),
            "status": a.status,
            "decided_at": a.decided_at.isoformat() if a.decided_at else None
        }
        for a in apps
    ]
    
    return {
        "user_id": user.pk,
        "year": target_year,
        "balances": balance_data,
        "history": history
    }

def export_leave_summary_csv(user, year=None):
    """
    Generates a CSV string of the leave summary.
    """
    import io
    import csv
    
    summary = get_leave_summary(user, year)
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header and User Info
    writer.writerow(["Leave Summary Report"])
    writer.writerow(["User ID", summary["user_id"]])
    writer.writerow(["Year", summary["year"]])
    writer.writerow([])
    
    # Balances Section
    writer.writerow(["--- Balances ---"])
    writer.writerow(["Type", "Entitled", "Used", "Lapsed", "Available"])
    for b in summary["balances"]:
        writer.writerow([b["type"], b["entitled"], b["used"], b["lapsed"], b["available"]])
    
    writer.writerow([])
    
    # History Section
    writer.writerow(["--- Application History ---"])
    writer.writerow(["ID", "Type", "Start", "End", "Days", "Status", "Decision Date"])
    for h in summary["history"]:
        writer.writerow([h["id"], h["type"], h["start"], h["end"], h["days"], h["status"], h["decided_at"]])
    
    return output.getvalue()

def ensure_balances(user, year):
    balances = []
    for leave_type in ANNUAL_ENTITLEMENT:
        balance, created = LeaveBalance.objects.get_or_create(
            user=user,
            year=year,
            leave_type=leave_type,
            defaults={'entitled': ANNUAL_ENTITLEMENT[leave_type]}
        )
        balances.append(balance)
    return balances

def submit_application(user, leave_type, start_date, end_date, half_day="NONE",
                       special_purpose="", special_purpose_admissible=False, substitute_id=None):
    with transaction.atomic():
        days_by_year = split_days_by_year(start_date, end_date, half_day)
        total_days = sum(days_by_year.values())

        for year, days in days_by_year.items():
            balances = ensure_balances(user, year)
            balance = next((b for b in balances if b.leave_type == leave_type), None)
            if balance is None:
                raise ValueError(f"Unknown leave type for year {year}")

            pending = LeaveApplication.objects.filter(
                user=user, leave_type=leave_type, status="PENDING",
                start_date__year=year,
            ).aggregate(total=Sum("days"))["total"] or Decimal("0")
            validate_balance(days, balance.entitled, balance.used + pending)

        if leave_type == "RH":
            # Use the new LeaveCalendar system
            calendar = LeaveCalendar.objects.filter(
                year=start_date.year, status="PUBLISHED"
            ).first()
            if not calendar:
                raise ValueError(f"No published leave calendar for {start_date.year}")
            
            published_rh_dates = set(calendar.dates.filter(
                kind="RESTRICTED"
            ).values_list("date", flat=True))
            
            for day in (start_date, end_date):
                validate_rh_date(day, published_rh_dates)

        if leave_type == "SCL":
            # SCL limit is annual. Check it for the starting year.
            used_scl = LeaveApplication.objects.filter(
                user=user, leave_type="SCL",
                status__in=["PENDING", "APPROVED"],
                start_date__year=start_date.year,
            ).aggregate(total=Sum("days"))["total"] or Decimal("0")
            validate_scl(total_days, used_scl, special_purpose_admissible)

        for other in LeaveApplication.objects.filter(
                user=user, status__in=["PENDING", "APPROVED"],
                start_date__lte=end_date, end_date__gte=start_date):
            if half_days_overlap(start_date, end_date, half_day,
                                 other.start_date, other.end_date, other.half_day):
                raise ValueError("Overlaps with an existing application")

        return LeaveApplication.objects.create(
            user=user, leave_type=leave_type, start_date=start_date,
            end_date=end_date, half_day=half_day, days=total_days,
            special_purpose=special_purpose,
            special_purpose_admissible=special_purpose_admissible,
            substitute_id=substitute_id,
        )

def approve_application(application):
    with transaction.atomic():
        if application.status != 'PENDING':
            raise ValueError("Application is not pending")

        # Split the total days by year to deduct from the correct balances
        days_by_year = split_days_by_year(application.start_date, application.end_date, application.half_day)
        
        for year, days in days_by_year.items():
            balance = LeaveBalance.objects.get(
                user=application.user,
                year=year,
                leave_type=application.leave_type
            )
            
            balance.used += days
            balance.save()

            LeaveTransaction.objects.create(
                balance=balance,
                application=application,
                kind='DEDUCT',
                days=days
            )

        application.status = 'APPROVED'
        application.save()

def run_year_end_lapse(year):
    with transaction.atomic():
        for leave_type in ['CL', 'RH']:
            balances = LeaveBalance.objects.filter(
                user__isnull=False,
                year=year,
                leave_type=leave_type
            )

            for balance in balances:
                lapse = year_end_lapse(balance.entitled, balance.used) - balance.lapsed
                if lapse > 0:
                    balance.lapsed += lapse
                    balance.save()

                    LeaveTransaction.objects.create(
                        balance=balance,
                        kind='LAPSE',
                        days=lapse
                    )
