from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0063_entry_and_payment_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="seasonsettings",
            name="rider_stats_monthly_price",
            field=models.IntegerField(default=50),
        ),
    ]
