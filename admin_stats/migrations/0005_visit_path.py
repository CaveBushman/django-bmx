from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admin_stats", "0004_visit_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="visit",
            name="path",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
