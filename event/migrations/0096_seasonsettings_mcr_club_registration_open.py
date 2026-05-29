from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0095_remove_eventexportjob_evt_expjob_evt_type_stat_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="seasonsettings",
            name="mcr_club_registration_open",
            field=models.BooleanField(default=True),
        ),
    ]
