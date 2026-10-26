from django.db import migrations


def seed_categories(apps, schema_editor):
    LeaveType = apps.get_model("leave", "LeaveType")
    categories = (
        ("CL", "Casual Leave", "8", ["faculty", "staff"], False, True),
        ("RH", "Restricted Holiday", "2", ["faculty", "staff"], False, False),
        ("SCL", "Special Casual Leave", "15", ["faculty", "staff"], False, False),
        ("EL", "Earned Leave", "30", ["staff"], True, False),
        ("COL", "Commuted Leave", "20", ["faculty", "staff"], True, False),
        ("VL", "Vacation Leave", "60", ["faculty"], True, False),
    )
    for code, name, entitlement, eligible, continuous, half_day in categories:
        LeaveType.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "annual_entitlement": entitlement,
                "carry_forward_limit": "0",
                "eligible_kinds": eligible,
                "count_continuously": continuous,
                "allows_half_day": half_day,
                "is_active": True,
                "is_paid": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("leave", "0002_elm_workflow")]
    operations = [migrations.RunPython(seed_categories, migrations.RunPython.noop)]
