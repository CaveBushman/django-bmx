from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0065_event_flexibee_export"),
        ("finance", "0005_eventinvoiceoverride_manual_amounts"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventCashReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(max_length=255, unique=True)),
                ("issue_date", models.DateField()),
                ("rider_name", models.CharField(max_length=255)),
                ("uci_id", models.CharField(blank=True, max_length=64)),
                ("category", models.CharField(blank=True, max_length=255)),
                ("country", models.CharField(blank=True, max_length=255)),
                ("note", models.TextField(blank=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("pdf", models.FileField(blank=True, null=True, upload_to="cash-receipts/pdf/")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cash_receipts",
                        to="event.event",
                    ),
                ),
            ],
            options={
                "verbose_name": "Pokladní doklad",
                "verbose_name_plural": "Pokladní doklady",
                "ordering": ["-issue_date", "-created"],
            },
        ),
    ]
