from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0072_alter_eventproposition_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="racerun",
            name="category",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="racerun",
            name="heat_code",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="racerun",
            name="plate",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
