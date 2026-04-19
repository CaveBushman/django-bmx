from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("eshop", "0010_product_structure_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockReservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_key", models.CharField(db_index=True, max_length=40, verbose_name="Session key")),
                ("quantity", models.PositiveIntegerField(default=1, verbose_name="Počet kusů")),
                ("expires_at", models.DateTimeField(verbose_name="Platí do")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stock_reservations",
                        to="eshop.productvariant",
                        verbose_name="Varianta",
                    ),
                ),
            ],
            options={
                "verbose_name": "Rezervace skladu",
                "verbose_name_plural": "Rezervace skladu",
                "ordering": ["expires_at"],
                "unique_together": {("session_key", "variant")},
            },
        ),
    ]
