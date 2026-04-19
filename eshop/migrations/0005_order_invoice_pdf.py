from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eshop", "0004_order_event_alter_order_city_alter_order_street_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="invoice_pdf",
            field=models.FileField(blank=True, upload_to="eshop/invoices/", verbose_name="Faktura PDF"),
        ),
    ]
