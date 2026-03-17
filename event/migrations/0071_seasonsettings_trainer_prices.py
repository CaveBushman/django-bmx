from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0070_eventproposition"),
    ]

    operations = [
        migrations.AddField(
            model_name="seasonsettings",
            name="trainer_club_stats_monthly_price",
            field=models.IntegerField(default=250),
        ),
        migrations.AddField(
            model_name="seasonsettings",
            name="trainer_extended_monthly_price",
            field=models.IntegerField(default=500),
        ),
    ]
