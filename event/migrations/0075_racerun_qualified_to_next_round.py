from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0074_racerun_independent_from_result"),
    ]

    operations = [
        migrations.AddField(
            model_name="racerun",
            name="qualified_to_next_round",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
