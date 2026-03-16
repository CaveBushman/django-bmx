from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0007_eventcashreceipt_customer_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventcashreceipt",
            name="customer_city",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="eventcashreceipt",
            name="customer_country",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="eventcashreceipt",
            name="customer_street",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="eventcashreceipt",
            name="customer_zip_code",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.RemoveField(
            model_name="eventcashreceipt",
            name="country",
        ),
    ]
