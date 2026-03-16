from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("event", "0065_event_flexibee_export"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommissionTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Nazev ukolu")),
                ("description", models.TextField(blank=True, verbose_name="Popis")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "Novy"),
                            ("in_progress", "Rozpracovano"),
                            ("waiting", "Ceka na reakci"),
                            ("done", "Splneno"),
                            ("cancelled", "Zruseno"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=20,
                        verbose_name="Stav",
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[
                            ("low", "Nizka"),
                            ("medium", "Stredni"),
                            ("high", "Vysoka"),
                            ("urgent", "Urgentni"),
                        ],
                        db_index=True,
                        default="medium",
                        max_length=20,
                        verbose_name="Priorita",
                    ),
                ),
                ("due_date", models.DateField(blank=True, db_index=True, null=True, verbose_name="Termin")),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="Splneno")),
                ("created", models.DateTimeField(auto_now_add=True, null=True, verbose_name="Vytvoreno")),
                ("updated", models.DateTimeField(auto_now=True, null=True, verbose_name="Upraveno")),
                (
                    "assignee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_commission_tasks",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Resitel",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_commission_tasks",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Zadal",
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="commission_tasks",
                        to="event.event",
                        verbose_name="Souvisejici zavod",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ukol komise",
                "verbose_name_plural": "Ukoly komise",
                "ordering": ("due_date", "-created"),
            },
        ),
    ]
