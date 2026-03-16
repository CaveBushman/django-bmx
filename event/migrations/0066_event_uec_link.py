from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0065_event_flexibee_export"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="uec_link",
            field=models.URLField(
                blank=True,
                help_text="Externí registrace na UEC",
                max_length=500,
                null=True,
            ),
        ),
    ]
