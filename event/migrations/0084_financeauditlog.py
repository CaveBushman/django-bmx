from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0083_entryauditlog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FinanceAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("created", "Vytvoření"), ("updated", "Úprava"), ("deleted", "Smazání")], max_length=20)),
                ("source", models.CharField(default="admin", max_length=64)),
                ("target_model", models.CharField(max_length=64)),
                ("target_object_id", models.IntegerField(blank=True, null=True)),
                ("target_user_id_snapshot", models.IntegerField(blank=True, null=True)),
                ("amount_snapshot", models.IntegerField(default=0)),
                ("transaction_kind_snapshot", models.CharField(blank=True, default="", max_length=64)),
                ("payment_complete_snapshot", models.BooleanField(blank=True, null=True)),
                ("payment_valid_snapshot", models.BooleanField(blank=True, null=True)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="finance_audit_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Audit financí",
                "verbose_name_plural": "Audit financí",
            },
        ),
        migrations.AddIndex(
            model_name="financeauditlog",
            index=models.Index(fields=["target_model", "created_at"], name="event_finaudit_model_date"),
        ),
        migrations.AddIndex(
            model_name="financeauditlog",
            index=models.Index(fields=["target_object_id", "created_at"], name="event_finaudit_object_date"),
        ),
    ]
