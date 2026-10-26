from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="LeaveType", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("code", models.SlugField(max_length=24, unique=True)), ("name", models.CharField(max_length=80)),
            ("annual_entitlement", models.DecimalField(decimal_places=2, default=0, max_digits=6)),
            ("carry_forward_limit", models.DecimalField(decimal_places=2, default=0, max_digits=6)),
            ("requires_document", models.BooleanField(default=False)), ("is_paid", models.BooleanField(default=True)),
            ("is_active", models.BooleanField(default=True)),
        ], options={"db_table": "leave_type", "ordering": ["name"]}),
        migrations.CreateModel(name="LeaveBalance", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("employee_id", models.PositiveIntegerField(db_index=True)), ("year", models.PositiveSmallIntegerField(db_index=True)),
            ("opening", models.DecimalField(decimal_places=2, default=0, max_digits=7)),
            ("accrued", models.DecimalField(decimal_places=2, default=0, max_digits=7)),
            ("adjusted", models.DecimalField(decimal_places=2, default=0, max_digits=7)),
            ("consumed", models.DecimalField(decimal_places=2, default=0, max_digits=7)),
            ("leave_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="balances", to="leave.leavetype")),
        ], options={"db_table": "leave_balance"}),
        migrations.AddConstraint(model_name="leavebalance", constraint=models.UniqueConstraint(fields=("employee_id", "leave_type", "year"), name="leave_balance_employee_type_year_uniq")),
        migrations.CreateModel(name="LeaveRequest", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("employee_id", models.PositiveIntegerField(db_index=True)), ("start_date", models.DateField(db_index=True)),
            ("end_date", models.DateField(db_index=True)), ("days", models.DecimalField(decimal_places=2, max_digits=6)),
            ("reason", models.TextField(max_length=1000)), ("document_url", models.URLField(blank=True, max_length=500)),
            ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled")], db_index=True, default="pending", max_length=12)),
            ("reviewer_id", models.PositiveIntegerField(blank=True, null=True)), ("reviewer_note", models.CharField(blank=True, max_length=500)),
            ("decided_at", models.DateTimeField(blank=True, null=True)),
            ("leave_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requests", to="leave.leavetype")),
        ], options={"db_table": "leave_request", "ordering": ["-created_at"]}),
        migrations.CreateModel(name="LeaveLedger", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("employee_id", models.PositiveIntegerField(db_index=True)), ("year", models.PositiveSmallIntegerField()),
            ("amount", models.DecimalField(decimal_places=2, max_digits=7)), ("kind", models.CharField(max_length=20)),
            ("reference", models.CharField(blank=True, max_length=100)), ("actor_id", models.PositiveIntegerField(blank=True, null=True)),
            ("note", models.CharField(blank=True, max_length=500)),
            ("leave_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="leave.leavetype")),
        ], options={"db_table": "leave_ledger", "ordering": ["-created_at"]}),
    ]
