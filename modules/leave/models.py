from django.db import models

from core.db.mixins import TimeStampedModel


class LeaveType(TimeStampedModel):
    CATEGORIES = [(code, code) for code in ("CL", "RH", "SCL", "EL", "COL", "VL")]
    code = models.SlugField(max_length=24, unique=True)
    name = models.CharField(max_length=80)
    annual_entitlement = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    carry_forward_limit = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    requires_document = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    eligible_kinds = models.JSONField(default=list, blank=True)
    count_continuously = models.BooleanField(default=False)
    allows_half_day = models.BooleanField(default=False)

    class Meta:
        db_table = "leave_type"
        ordering = ["name"]


class LeaveBalance(TimeStampedModel):
    employee_id = models.PositiveIntegerField(db_index=True)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="balances")
    year = models.PositiveSmallIntegerField(db_index=True)
    opening = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    accrued = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    adjusted = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    consumed = models.DecimalField(max_digits=7, decimal_places=2, default=0)

    class Meta:
        db_table = "leave_balance"
        constraints = [models.UniqueConstraint(fields=["employee_id", "leave_type", "year"], name="leave_balance_employee_type_year_uniq")]

    @property
    def available(self):
        return self.opening + self.accrued + self.adjusted - self.consumed


class LeaveRequest(TimeStampedModel):
    STATUS = [(s, s.replace("_", " ").title()) for s in (
        "pending", "approved", "rejected", "withdrawn", "cancelled",
        "cancellation_pending", "extension_pending", "resumption_pending",
        "extended", "recorded_offline",
    )]
    REQUEST_KINDS = [(s, s.title()) for s in ("new", "cancellation", "extension", "resumption", "offline")]
    employee_id = models.PositiveIntegerField(db_index=True)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    parent_request = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="related_requests")
    request_kind = models.CharField(max_length=16, choices=REQUEST_KINDS, default="new", db_index=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    days = models.DecimalField(max_digits=6, decimal_places=2)
    reason = models.TextField(max_length=1000)
    document_url = models.URLField(max_length=500, blank=True)
    half_day = models.CharField(max_length=8, blank=True, choices=[("first", "First half"), ("second", "Second half")])
    station_leave = models.BooleanField(default=False)
    station_leave_details = models.CharField(max_length=500, blank=True)
    substitute_id = models.PositiveIntegerField(null=True, blank=True)
    substitute_status = models.CharField(max_length=12, blank=True, choices=[("pending", "Pending"), ("accepted", "Accepted"), ("declined", "Declined")])
    unit_name = models.CharField(max_length=120, blank=True)
    workflow_stage = models.CharField(max_length=32, blank=True)
    unit_head_recommendation = models.CharField(max_length=16, blank=True, choices=[("recommended", "Recommended"), ("not_recommended", "Not recommended")])
    director_self_sanction = models.BooleanField(default=False)
    status = models.CharField(max_length=24, choices=STATUS, default="pending", db_index=True)
    reviewer_id = models.PositiveIntegerField(null=True, blank=True)
    reviewer_note = models.CharField(max_length=500, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    actual_return_date = models.DateField(null=True, blank=True)
    resumption_note = models.CharField(max_length=500, blank=True)
    offline_reference = models.CharField(max_length=200, blank=True)
    offline_evidence_url = models.URLField(max_length=500, blank=True)
    balance_posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "leave_request"
        ordering = ["-created_at"]


class LeaveLedger(TimeStampedModel):
    employee_id = models.PositiveIntegerField(db_index=True)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT)
    year = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=7, decimal_places=2)
    kind = models.CharField(max_length=20)
    reference = models.CharField(max_length=100, blank=True)
    actor_id = models.PositiveIntegerField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "leave_ledger"
        ordering = ["-created_at"]


class LeaveApprovalTask(TimeStampedModel):
    """The current actionable approval or substitute task."""
    ACTIONS = [(s, s.replace("_", " ").title()) for s in (
        "substitute_response", "unit_head_review", "establishment_review", "sanction",
        "cancellation_decision", "extension_decision", "resumption_review",
    )]
    STATUS = [(s, s.title()) for s in ("pending", "completed", "withdrawn", "escalated")]
    leave_request = models.ForeignKey(LeaveRequest, on_delete=models.CASCADE, related_name="tasks")
    action = models.CharField(max_length=32, choices=ACTIONS)
    authority_role = models.CharField(max_length=80, blank=True)
    assigned_user_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS, default="pending", db_index=True)
    assigned_at = models.DateTimeField()
    reminder_at = models.DateTimeField(null=True, blank=True)
    escalation_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    decision = models.CharField(max_length=20, blank=True)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "leave_approval_task"
        ordering = ["assigned_at"]
        indexes = [models.Index(fields=["status", "escalation_at"], name="leave_task_sla_idx")]


class LeaveTransition(models.Model):
    leave_request = models.ForeignKey(LeaveRequest, on_delete=models.CASCADE, related_name="transitions")
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24)
    actor_id = models.PositiveIntegerField(null=True, blank=True)
    action = models.CharField(max_length=32)
    note = models.CharField(max_length=500, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "leave_transition"
        ordering = ["at"]


class LeaveAuthority(TimeStampedModel):
    """Configured unit/category route; identities remain IAM-owned integers."""
    unit_name = models.CharField(max_length=120, blank=True, db_index=True)
    category = models.CharField(max_length=8, choices=LeaveType.CATEGORIES)
    step_order = models.PositiveSmallIntegerField()
    authority_role = models.CharField(max_length=80)
    assigned_user_id = models.PositiveIntegerField(null=True, blank=True)
    is_establishment = models.BooleanField(default=False)
    optional_step = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "leave_authority"
        ordering = ["unit_name", "category", "step_order"]
        constraints = [models.UniqueConstraint(fields=["unit_name", "category", "step_order"], name="leave_authority_route_step_uniq")]


class LeaveCalendar(TimeStampedModel):
    name = models.CharField(max_length=120)
    year = models.PositiveSmallIntegerField(db_index=True)
    status = models.CharField(max_length=12, choices=[("draft", "Draft"), ("published", "Published"), ("superseded", "Superseded")], default="draft")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "leave_calendar"
        constraints = [models.UniqueConstraint(fields=["year", "status"], condition=models.Q(status="published"), name="leave_calendar_one_published_year")]


class LeaveCalendarDate(models.Model):
    calendar = models.ForeignKey(LeaveCalendar, on_delete=models.CASCADE, related_name="dates")
    date = models.DateField()
    kind = models.CharField(max_length=16, choices=[("holiday", "Closed holiday"), ("restricted", "Restricted holiday")])
    label = models.CharField(max_length=120)

    class Meta:
        db_table = "leave_calendar_date"
        constraints = [models.UniqueConstraint(fields=["calendar", "date", "kind"], name="leave_calendar_date_uniq")]


class LeaveVacationPeriod(models.Model):
    start_date = models.DateField()
    end_date = models.DateField()
    source_reference = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "leave_vacation_period"
        ordering = ["start_date"]


class LeaveWorkflowConfig(TimeStampedModel):
    reminder_hours = models.PositiveSmallIntegerField(default=24)
    escalation_hours = models.PositiveSmallIntegerField(default=72)
    escalation_authority_role = models.CharField(max_length=80, blank=True)
    establishment_step_enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "leave_workflow_config"


class LeaveYearEndRun(TimeStampedModel):
    year = models.PositiveSmallIntegerField(unique=True)
    started_by = models.PositiveIntegerField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    exceptions = models.JSONField(default=list, blank=True)
    processed_accounts = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "leave_year_end_run"
