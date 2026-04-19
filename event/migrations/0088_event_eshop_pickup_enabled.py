# Generated manually for e-shop pickup event gating.

from django.db import migrations, models
import django.utils.translation


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0087_alter_credittransaction_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="eshop_pickup_enabled",
            field=models.BooleanField(
                default=False,
                help_text=django.utils.translation.gettext_lazy(
                    "Zaškrtněte pouze u závodů, kde bude možné předávat objednávky z e-shopu."
                ),
                verbose_name=django.utils.translation.gettext_lazy("Výdej e-shop zboží"),
            ),
        ),
    ]
