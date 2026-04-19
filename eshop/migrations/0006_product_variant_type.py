from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eshop", "0005_order_invoice_pdf"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="variant_type",
            field=models.CharField(
                choices=[("size", "Velikost"), ("color", "Barva"), ("other", "Jiné")],
                default="size",
                max_length=10,
                verbose_name="Typ varianty",
            ),
        ),
    ]
