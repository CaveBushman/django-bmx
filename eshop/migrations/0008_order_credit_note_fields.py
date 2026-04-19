from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eshop", "0007_order_invoice_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="credit_note_number",
            field=models.CharField(blank=True, max_length=20, unique=True, verbose_name="Číslo dobropisu"),
        ),
        migrations.AddField(
            model_name="order",
            name="credit_note_pdf",
            field=models.FileField(blank=True, upload_to="eshop/credit-notes/", verbose_name="Dobropis PDF"),
        ),
    ]
