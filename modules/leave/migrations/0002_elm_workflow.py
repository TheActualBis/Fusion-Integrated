from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("leave", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="leavetype", name="eligible_kinds",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="leavetype", name="count_continuously",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="leavetype", name="allows_half_day",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="leaverequest", name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"), ("approved", "Approved"),
                    ("rejected", "Rejected"), ("withdrawn", "Withdrawn"),
                    ("cancelled", "Cancelled"),
                    ("cancellation_pending", "Cancellation Pending"),
                    ("extension_pending", "Extension Pending"),
                    ("resumption_pending", "Resumption Pending"),
                    ("extended", "Extended"), ("recorded_offline", "Recorded Offline"),
                ], db_index=True, default="pending", max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="leaverequest", name="parent_request",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="related_requests", to="leave.leaverequest"),
        ),
        migrations.AddField(
            model_name="leaverequest", name="request_kind",
            field=models.CharField(choices=[("new", "New"), ("cancellation", "Cancellation"),
                ("extension", "Extension"), ("resumption", "Resumption"), ("offline", "Offline")],
                db_index=True, default="new", max_length=16),
        ),
        migrations.AddField(
            model_name="leaverequest", name="half_day",
            field=models.CharField(blank=True, choices=[("first", "First half"), ("second", "Second half")], max_length=8),
        ),
        migrations.AddField(
            model_name="leaverequest", name="station_leave",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="leaverequest", name="station_leave_details",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="leaverequest", name="substitute_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="leaverequest", name="substitute_status",
            field=models.CharField(blank=True, choices=[("pending", "Pending"), ("accepted", "Accepted"),
                ("declined", "Declined")], max_length=12),
        ),
        migrations.AddField(
            model_name="leaverequest", name="unit_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="leaverequest", name="workflow_stage",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="leaverequest", name="unit_head_recommendation",
            field=models.CharField(blank=True, choices=[("recommended", "Recommended"),
                ("not_recommended", "Not recommended")], max_length=16),
        ),
        migrations.AddField(
            model_name="leaverequest", name="actual_return_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="leaverequest", name="resumption_note",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="leaverequest", name="offline_reference",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="leaverequest", name="offline_evidence_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="leaverequest", name="balance_posted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="LeaveApprovalTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action", models.CharField(choices=[("substitute_response", "Substitute Response"),
                    ("unit_head_review", "Unit Head Review"), ("establishment_review", "Establishment Review"),
                    ("sanction", "Sanction"), ("cancellation_decision", "Cancellation Decision"),
                    ("extension_decision", "Extension Decision"), ("resumption_review", "Resumption Review")], max_length=32)),
                ("authority_role", models.CharField(blank=True, max_length=80)),
                ("assigned_user_id", models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("completed", "Completed"),
                    ("withdrawn", "Withdrawn"), ("escalated", "Escalated")], db_index=True, default="pending", max_length=12)),
                ("assigned_at", models.DateTimeField()),
                ("reminder_at", models.DateTimeField(blank=True, null=True)),
                ("escalation_at", models.DateTimeField(blank=True, null=True)),
                ("reminder_sent_at", models.DateTimeField(blank=True, null=True)),
                ("escalated_at", models.DateTimeField(blank=True, null=True)),
                ("decision", models.CharField(blank=True, max_length=20)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("leave_request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="tasks", to="leave.leaverequest")),
            ], options={"db_table": "leave_approval_task", "ordering": ["assigned_at"]},
        ),
        migrations.AddIndex(model_name="leaveapprovaltask", index=models.Index(fields=["status", "escalation_at"], name="leave_task_sla_idx")),
        migrations.CreateModel(
            name="LeaveTransition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_status", models.CharField(blank=True, max_length=24)),
                ("to_status", models.CharField(max_length=24)),
                ("actor_id", models.PositiveIntegerField(blank=True, null=True)),
                ("action", models.CharField(max_length=32)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("at", models.DateTimeField(auto_now_add=True)),
                ("leave_request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="transitions", to="leave.leaverequest")),
            ], options={"db_table": "leave_transition", "ordering": ["at"]},
        ),
        migrations.CreateModel(
            name="LeaveAuthority",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("unit_name", models.CharField(blank=True, db_index=True, max_length=120)),
                ("category", models.CharField(choices=[("CL", "CL"), ("RH", "RH"), ("SCL", "SCL"),
                    ("EL", "EL"), ("COL", "COL"), ("VL", "VL")], max_length=8)),
                ("step_order", models.PositiveSmallIntegerField()),
                ("authority_role", models.CharField(max_length=80)),
                ("assigned_user_id", models.PositiveIntegerField(blank=True, null=True)),
                ("is_establishment", models.BooleanField(default=False)),
                ("optional_step", models.BooleanField(default=False)), ("is_active", models.BooleanField(default=True)),
            ], options={"db_table": "leave_authority", "ordering": ["unit_name", "category", "step_order"]},
        ),
        migrations.AddConstraint(model_name="leaveauthority", constraint=models.UniqueConstraint(fields=("unit_name", "category", "step_order"), name="leave_authority_route_step_uniq")),
        migrations.CreateModel(
            name="LeaveCalendar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)), ("year", models.PositiveSmallIntegerField(db_index=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("superseded", "Superseded")], default="draft", max_length=12)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
            ], options={"db_table": "leave_calendar"},
        ),
        migrations.AddConstraint(model_name="leavecalendar", constraint=models.UniqueConstraint(condition=models.Q(status="published"), fields=("year", "status"), name="leave_calendar_one_published_year")),
        migrations.CreateModel(
            name="LeaveCalendarDate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("kind", models.CharField(choices=[("holiday", "Closed holiday"), ("restricted", "Restricted holiday")], max_length=16)),
                ("label", models.CharField(max_length=120)),
                ("calendar", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dates", to="leave.leavecalendar")),
            ], options={"db_table": "leave_calendar_date"},
        ),
        migrations.AddConstraint(model_name="leavecalendardate", constraint=models.UniqueConstraint(fields=("calendar", "date", "kind"), name="leave_calendar_date_uniq")),
        migrations.CreateModel(
            name="LeaveVacationPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField()), ("end_date", models.DateField()),
                ("source_reference", models.CharField(blank=True, max_length=200)),
            ], options={"db_table": "leave_vacation_period", "ordering": ["start_date"]},
        ),
        migrations.CreateModel(
            name="LeaveWorkflowConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("reminder_hours", models.PositiveSmallIntegerField(default=24)),
                ("escalation_hours", models.PositiveSmallIntegerField(default=72)),
                ("escalation_authority_role", models.CharField(blank=True, max_length=80)),
                ("establishment_step_enabled", models.BooleanField(default=False)),
            ], options={"db_table": "leave_workflow_config"},
        ),
        migrations.CreateModel(
            name="LeaveYearEndRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("year", models.PositiveSmallIntegerField(unique=True)), ("started_by", models.PositiveIntegerField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)), ("exceptions", models.JSONField(blank=True, default=list)),
            ], options={"db_table": "leave_year_end_run"},
        ),
    ]
