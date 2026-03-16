from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("club", "0010_rename_riders_on_event_club_riders_on_events"),
    ]

    operations = [
        migrations.AddField(
            model_name="club",
            name="billing_email",
            field=models.EmailField(blank=True, max_length=255),
        ),
    ]
