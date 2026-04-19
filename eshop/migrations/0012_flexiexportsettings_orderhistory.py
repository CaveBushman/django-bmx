# Generated manually for e-shop order history and ABRA Flexi configuration.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("eshop", "0011_stockreservation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FlexiExportSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="Výchozí nastavení", max_length=80, verbose_name="Název")),
                ("invoice_document_type", models.CharField(default="FAKTURA", max_length=40, verbose_name="Typ faktury")),
                ("credit_note_document_type", models.CharField(default="DOBROPIS", max_length=40, verbose_name="Typ dobropisu")),
                ("price_type_code", models.CharField(default="typCeny.bezDph", max_length=60, verbose_name="Typ ceny")),
                ("vat_rate_code", models.CharField(default="typSzbDph.dphOsv", max_length=60, verbose_name="Sazba DPH")),
                ("item_type_code", models.CharField(default="typPolozky.obecny", max_length=60, verbose_name="Typ položky")),
                ("payment_status_code", models.CharField(default="stavUhr.uhrazeno", max_length=60, verbose_name="Stav úhrady")),
                ("currency_code", models.CharField(default="CZK", max_length=12, verbose_name="Měna")),
                ("country_code", models.CharField(default="CZ", max_length=12, verbose_name="Stát")),
                ("unit_code", models.CharField(default="KS", max_length=12, verbose_name="Měrná jednotka")),
                ("center_code", models.CharField(blank=True, max_length=40, verbose_name="Středisko")),
                ("payment_method_code", models.CharField(blank=True, max_length=40, verbose_name="Forma úhrady")),
                ("vat_classification_code", models.CharField(blank=True, max_length=60, verbose_name="Členění DPH")),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "ABRA Flexi nastavení",
                "verbose_name_plural": "ABRA Flexi nastavení",
            },
        ),
        migrations.CreateModel(
            name="OrderHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("created", "Vytvořeno"),
                            ("credit_charged", "Kredit odečten"),
                            ("confirmed", "Potvrzeno"),
                            ("invoice_issued", "Faktura vystavena"),
                            ("shipped", "Odesláno"),
                            ("delivered", "Předáno"),
                            ("canceled", "Stornováno"),
                            ("credit_refunded", "Kredit vrácen"),
                            ("credit_note_issued", "Dobropis vystaven"),
                            ("note", "Poznámka"),
                        ],
                        max_length=32,
                        verbose_name="Akce",
                    ),
                ),
                ("note", models.TextField(blank=True, verbose_name="Poznámka")),
                ("created", models.DateTimeField(auto_now_add=True, verbose_name="Vytvořeno")),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="eshop_order_history_entries",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Provedl",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history",
                        to="eshop.order",
                        verbose_name="Objednávka",
                    ),
                ),
            ],
            options={
                "verbose_name": "Historie objednávky",
                "verbose_name_plural": "Historie objednávek",
                "ordering": ["-created", "-id"],
            },
        ),
    ]
