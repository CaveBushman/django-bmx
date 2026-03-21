from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0073_racerun_heat_code_plate_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="racerun",
            name="result",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="runs", to="event.result"),
        ),
        migrations.AddField(
            model_name="racerun",
            name="is_beginner",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="racerun",
            name="is_20",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
