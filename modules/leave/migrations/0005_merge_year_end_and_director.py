"""Join the independent year-end retry and Director-sanction migrations."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("leave", "0003_year_end_retry"),
        ("leave", "0004_director_self_sanction"),
    ]

    operations = []
