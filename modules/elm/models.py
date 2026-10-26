from django.db import models
from decimal import Decimal
from modules.directory.models import UserRef

ANNUAL_ENTITLEMENT = {
    'CL': 8,
    'RH': 2,
    'SCL': 15
}

class LeaveType(models.TextChoices):
    CL = 'CL', 'Casual Leave'
    RH = 'RH', 'Restricted Holiday'
    SCL = 'SCL', 'Special Casual Leave'

class LeaveBalance(models.Model):
    user = models.ForeignKey(UserRef, on_delete=models.PROTECT)
    year = models.IntegerField()
    leave_type = models.CharField(max_length=3, choices=LeaveType.choices)
    entitled = models.DecimalField(max_digits=4, decimal_places=1)
    used = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    lapsed = models.DecimalField(max_digits=4, decimal_places=1, default=0)

    class Meta:
        unique_together = ('user', 'year', 'leave_type')

class LeaveCalendar(models.Model):
    """A published set of holidays for a specific year."""
    year = models.PositiveSmallIntegerField(unique=True)
    status = models.CharField(
        max_length=12, 
        choices=[('DRAFT', 'Draft'), ('PUBLISHED', 'Published')], 
        default='DRAFT'
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Leave Calendar"

class LeaveCalendarDate(models.Model):
    """Specific holiday dates within a calendar."""
    calendar = models.ForeignKey(LeaveCalendar, on_delete=models.CASCADE, related_name="dates")
    date = models.DateField()
    kind = models.CharField(
        max_length=16, 
        choices=[('HOLIDAY', 'Closed Holiday'), ('RESTRICTED', 'Restricted Holiday')]
    )
    label = models.CharField(max_length=255)

    class Meta:
        unique_together = ("calendar", "date", "kind")

class LeaveApplicationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    WITHDRAWN = 'WITHDRAWN', 'Withdrawn'
    CANCELLED = 'CANCELLED', 'Cancelled'

class LeaveApplication(models.Model):
    user = models.ForeignKey(UserRef, on_delete=models.PROTECT)
    leave_type = models.CharField(max_length=3, choices=LeaveType.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    half_day = models.CharField(
        max_length=10,
        choices=[
            ('NONE', 'None'),
            ('FIRST', 'First Half'),
            ('SECOND', 'Second Half')
        ],
        default='NONE'
    )
    days = models.DecimalField(max_digits=4, decimal_places=1)
    special_purpose = models.TextField(blank=True)
    special_purpose_admissible = models.BooleanField(default=False)
    status = models.CharField(
        max_length=10,
        choices=LeaveApplicationStatus.choices,
        default='PENDING'
    )
    substitute_id = models.ForeignKey(
        UserRef, on_delete=models.SET_NULL, null=True, blank=True, related_name="substitute_leaves"
    )
    substitute_status = models.CharField(
        max_length=12,
        choices=[('PENDING', 'Pending'), ('ACCEPTED', 'Accepted'), ('DECLINED', 'Declined')],
        default='PENDING',
        blank=True
    )
    reviewer = models.ForeignKey(
        UserRef, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_leaves"
    )
    reviewer_note = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    actual_return_date = models.DateField(null=True, blank=True)
    resumption_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class LeaveTransaction(models.Model):
    balance = models.ForeignKey(LeaveBalance, on_delete=models.CASCADE)
    application = models.ForeignKey(LeaveApplication, on_delete=models.SET_NULL, null=True)
    kind = models.CharField(
        max_length=10,
        choices=[
            ('DEDUCT', 'Deduct'),
            ('LAPSE', 'Lapse')
        ]
    )
    days = models.DecimalField(max_digits=4, decimal_places=1)
    created_at = models.DateTimeField(auto_now_add=True)

class LeaveApprovalTask(models.Model):
    """Tracks a specific approval step for a leave application."""
    application = models.ForeignKey(LeaveApplication, on_delete=models.CASCADE, related_name="approval_tasks")
    action = models.CharField(max_length=32) # e.g., 'review', 'sanction'
    authority_role = models.CharField(max_length=80) # Role required to perform the action
    assigned_user = models.ForeignKey(UserRef, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(
        max_length=12,
        choices=[('PENDING', 'Pending'), ('COMPLETED', 'Completed'), ('WITHDRAWN', 'Withdrawn')],
        default='PENDING'
    )
    decision = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    reminder_at = models.DateTimeField(null=True, blank=True)
    escalation_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

class LeaveAuthority(models.Model):
    """Configured routing for leave approvals."""
    unit_name = models.CharField(max_length=120, db_index=True, blank=True)
    leave_type = models.CharField(max_length=3, choices=LeaveType.choices)
    step_order = models.PositiveSmallIntegerField()
    authority_role = models.CharField(max_length=80)
    assigned_user = models.ForeignKey(UserRef, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["unit_name", "step_order"]
        unique_together = ("unit_name", "leave_type", "step_order")

class LeaveWorkflowConfig(models.Model):
    """Global settings for leave reminders and escalation."""
    reminder_hours = models.PositiveSmallIntegerField(default=24)
    escalation_hours = models.PositiveSmallIntegerField(default=72)
    establishment_step_enabled = models.BooleanField(default=False)
