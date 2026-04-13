from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_alter_avatarchangerequest_status"),
        ("event", "0082_credittransaction_kind_and_source_entry"),
    ]

    operations = [
        migrations.CreateModel(
            name="EntryAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("checkout_changed", "Změna checkout")], max_length=40)),
                ("source", models.CharField(default="system", max_length=64)),
                ("old_checkout", models.BooleanField(default=False)),
                ("new_checkout", models.BooleanField(default=False)),
                ("payment_complete", models.BooleanField(default=False)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("entry_id_snapshot", models.IntegerField(blank=True, null=True)),
                ("entry_user_id_snapshot", models.IntegerField(blank=True, null=True)),
                ("event_name_snapshot", models.CharField(blank=True, default="", max_length=255)),
                ("rider_name_snapshot", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="entry_audit_logs", to="accounts.account")),
                ("entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_logs", to="event.entry")),
            ],
            options={
                "verbose_name": "Audit registrace",
                "verbose_name_plural": "Audit registrací",
            },
        ),
        migrations.AddIndex(
            model_name="entryauditlog",
            index=models.Index(fields=["action", "created_at"], name="event_entryaudit_action_date"),
        ),
        migrations.AddIndex(
            model_name="entryauditlog",
            index=models.Index(fields=["entry_id_snapshot", "created_at"], name="event_entryaudit_entry_date"),
        ),
    ]
