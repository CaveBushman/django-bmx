# Generated by Django 5.0.3 on 2024-05-13 14:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0038_remove_event_is_beginners_race"),
    ]

    operations = [
        migrations.CreateModel(
            name="SeasonSettings",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("year", models.IntegerField(default=2024)),
                ("qualify_to_cn", models.IntegerField(default=2)),
                ("best_cup", models.IntegerField(default=8)),
                ("best_cl", models.IntegerField(default=10)),
                ("best_ml", models.IntegerField(default=10)),
            ],
        ),
    ]
