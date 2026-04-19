from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eshop", "0009_order_delivery_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="collection",
            field=models.CharField(blank=True, max_length=100, verbose_name="Kolekce"),
        ),
        migrations.AddField(
            model_name="product",
            name="fit_note",
            field=models.CharField(blank=True, max_length=160, verbose_name="Poznámka ke střihu"),
        ),
        migrations.AddField(
            model_name="product",
            name="material",
            field=models.CharField(blank=True, max_length=160, verbose_name="Materiál"),
        ),
        migrations.AddField(
            model_name="product",
            name="pickup_note",
            field=models.CharField(blank=True, max_length=200, verbose_name="Poznámka k předání"),
        ),
        migrations.AddField(
            model_name="product",
            name="secondary_image",
            field=models.ImageField(blank=True, upload_to="eshop/products/", verbose_name="Doplňková fotka"),
        ),
        migrations.AddField(
            model_name="product",
            name="subtitle",
            field=models.CharField(blank=True, max_length=120, verbose_name="Krátký štítek"),
        ),
    ]
