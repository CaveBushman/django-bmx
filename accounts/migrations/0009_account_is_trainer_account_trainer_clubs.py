from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_account_club_account_is_club_manager"),
        ("club", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="is_trainer",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="account",
            name="trainer_clubs",
            field=models.ManyToManyField(blank=True, related_name="trainers", to="club.club"),
        ),
    ]
