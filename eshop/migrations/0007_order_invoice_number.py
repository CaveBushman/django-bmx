from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eshop", "0006_product_variant_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="invoice_number",
            field=models.CharField(blank=True, max_length=16, unique=True, verbose_name="Číslo faktury"),
        ),
    ]
