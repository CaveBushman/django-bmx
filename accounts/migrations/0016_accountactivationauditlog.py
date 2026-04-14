from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_account_search_text_normalized"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountActivationAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("sent", "Odeslána aktivace"), ("resent", "Znovu odeslána aktivace"), ("activated", "Účet aktivován"), ("cleaned_up", "Neaktivní účet odstraněn")], max_length=24)),
                ("source", models.CharField(default="system", max_length=64)),
                ("email_snapshot", models.EmailField(blank=True, default="", max_length=100)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="activation_audit_logs", to=settings.AUTH_USER_MODEL)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="performed_activation_audit_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Audit aktivace účtu",
                "verbose_name_plural": "Audit aktivací účtů",
            },
        ),
        migrations.AddIndex(
            model_name="accountactivationauditlog",
            index=models.Index(fields=["action", "created_at"], name="accounts_actaudit_action_date"),
        ),
        migrations.AddIndex(
            model_name="accountactivationauditlog",
            index=models.Index(fields=["email_snapshot", "created_at"], name="accounts_actaudit_email_date"),
        ),
    ]
