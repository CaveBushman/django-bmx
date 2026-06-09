from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eshop", "0014_stockalertrequest"),
    ]

    operations = [
        migrations.CreateModel(
            name="EshopSettings",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_public", models.BooleanField(default=False, help_text="Zaškrtni pro zpřístupnění e-shopu všem návštěvníkům. Jinak je viditelný jen administrátorům.", verbose_name="E-shop viditelný všem")),
                ("updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Nastavení e-shopu",
                "verbose_name_plural": "Nastavení e-shopu",
            },
        ),
    ]
