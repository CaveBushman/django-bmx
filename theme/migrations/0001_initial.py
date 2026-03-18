from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Sponsor",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120, verbose_name="Název")),
                ("alt_text", models.CharField(max_length=160, verbose_name="Alt text")),
                ("logo_light", models.ImageField(upload_to="images/sponsors/", verbose_name="Logo pro light režim")),
                (
                    "logo_dark",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="images/sponsors/",
                        verbose_name="Logo pro dark režim",
                    ),
                ),
                ("url", models.URLField(blank=True, verbose_name="Odkaz")),
                ("valid_from", models.DateField(verbose_name="Platí od")),
                ("valid_to", models.DateField(blank=True, null=True, verbose_name="Platí do")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Pořadí")),
                ("is_published", models.BooleanField(default=True, verbose_name="Publikováno")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Sponzor",
                "verbose_name_plural": "Sponzoři",
                "ordering": ["sort_order", "name"],
            },
        ),
    ]
