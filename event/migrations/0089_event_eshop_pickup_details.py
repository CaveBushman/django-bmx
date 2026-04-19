# Generated manually for e-shop pickup event details.

from django.db import migrations, models
import django.utils.translation


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0088_event_eshop_pickup_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="eshop_pickup_location",
            field=models.CharField(
                blank=True,
                max_length=160,
                verbose_name=django.utils.translation.gettext_lazy("Místo výdeje e-shopu"),
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="eshop_pickup_time",
            field=models.CharField(
                blank=True,
                max_length=120,
                verbose_name=django.utils.translation.gettext_lazy("Čas výdeje e-shopu"),
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="eshop_pickup_note",
            field=models.TextField(
                blank=True,
                verbose_name=django.utils.translation.gettext_lazy("Poznámka k výdeji e-shopu"),
            ),
        ),
    ]
