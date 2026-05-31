from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("club", "0013_mcrclubteam_mcrclubteammember"),
    ]

    operations = [
        migrations.AddField(
            model_name="club",
            name="opening_hours",
            field=models.TextField(blank=True, default=""),
        ),
    ]
