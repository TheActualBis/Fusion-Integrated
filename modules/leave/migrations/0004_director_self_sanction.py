from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leave", "0003_seed_elm_categories")]
    operations = [migrations.AddField(
        model_name="leaverequest", name="director_self_sanction",
        field=models.BooleanField(default=False),
    )]
