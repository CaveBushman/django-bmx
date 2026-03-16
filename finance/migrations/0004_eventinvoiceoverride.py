from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("club", "0011_club_billing_email"),
        ("event", "0065_event_flexibee_export"),
        ("finance", "0003_eventinvoice_export_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventInvoiceOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("manual_descriptions", models.TextField(blank=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("club", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invoice_overrides", to="club.club")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invoice_overrides", to="event.event")),
            ],
            options={
                "verbose_name": "Ruční úprava položek faktury",
                "verbose_name_plural": "Ruční úpravy položek faktur",
            },
        ),
        migrations.AddConstraint(
            model_name="eventinvoiceoverride",
            constraint=models.UniqueConstraint(fields=("event", "club"), name="finance_invoice_override_event_club_unique"),
        ),
    ]
