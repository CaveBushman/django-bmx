from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0086_alter_credittransaction_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="credittransaction",
            name="kind",
            field=models.CharField(
                choices=[
                    ("topup", "Dobití kreditu"),
                    ("checkout_refund", "Vrácení startovného po checkoutu"),
                    ("eshop_purchase", "Nákup v e-shopu"),
                    ("eshop_refund", "Storno objednávky e-shopu"),
                ],
                default="topup",
                max_length=32,
            ),
        ),
    ]
