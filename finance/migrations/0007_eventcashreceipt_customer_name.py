from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0006_eventcashreceipt"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventcashreceipt",
            name="customer_name",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
