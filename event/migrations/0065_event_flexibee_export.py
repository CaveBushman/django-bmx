from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0064_seasonsettings_rider_stats_monthly_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="flexibee_export",
            field=models.FileField(blank=True, null=True, upload_to="invoices/xml/"),
        ),
    ]
