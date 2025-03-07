# Generated by Django 5.0.3 on 2025-02-25 17:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0044_stripefee_alter_event_type_for_ranking"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="stripefee",
            options={
                "verbose_name": "Karetní poplatek",
                "verbose_name_plural": "Karetní poplatky (STRIPE)",
            },
        ),
        migrations.AddField(
            model_name="credittransaction",
            name="payment_intent",
            field=models.CharField(default="", max_length=255),
        ),
    ]
