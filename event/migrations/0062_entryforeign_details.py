from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0061_event_start_commissar"),
    ]

    operations = [
        migrations.AddField(
            model_name="entryforeign",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="entryforeign",
            name="is_elite",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="entryforeign",
            name="plate",
            field=models.CharField(blank=True, default="", max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="entryforeign",
            name="transponder_20",
            field=models.CharField(blank=True, default="", max_length=10, null=True),
        ),
        migrations.AddField(
            model_name="entryforeign",
            name="transponder_24",
            field=models.CharField(blank=True, default="", max_length=10, null=True),
        ),
    ]
