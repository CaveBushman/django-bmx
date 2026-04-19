from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("eshop", "0008_order_credit_note_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="delivered_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Předáno dne"),
        ),
        migrations.AddField(
            model_name="order",
            name="delivered_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="eshop_delivered_orders",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Předal",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="internal_note",
            field=models.TextField(blank=True, verbose_name="Interní poznámka"),
        ),
    ]
