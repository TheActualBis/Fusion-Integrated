from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leave", "0002_elm_workflow")]

    operations = [
        migrations.AddField(
            model_name="leaveyearendrun",
            name="processed_accounts",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
