from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0075_racerun_qualified_to_next_round"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="uci_code_men_elite",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="event",
            name="uci_code_men_junior",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="event",
            name="uci_code_men_under_23",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="event",
            name="uci_code_women_elite",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="event",
            name="uci_code_women_junior",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="event",
            name="uci_code_women_under_23",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="event",
            name="uci_event_code",
            field=models.CharField(blank=True, default="", help_text="UCI unique event code", max_length=64),
        ),
    ]
