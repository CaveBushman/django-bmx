from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("club", "0011_club_billing_email"),
    ]

    operations = [
        migrations.AlterField(
            model_name="club",
            name="riders_on_events",
            field=models.FileField(blank=True, null=True, upload_to="riders_in_events/"),
        ),
    ]
