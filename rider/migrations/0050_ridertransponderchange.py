from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_rename_user_credit_account_credit"),
        ("rider", "0049_riderstatssubscription_riderstatscharge"),
    ]

    operations = [
        migrations.CreateModel(
            name="RiderTransponderChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slot", models.CharField(choices=[("20", '20"'), ("24", '24"')], max_length=2)),
                ("old_transponder", models.CharField(blank=True, max_length=8, null=True)),
                ("new_transponder", models.CharField(blank=True, max_length=8, null=True)),
                ("changed_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transponder_changes_made", to="accounts.account")),
                ("rider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transponder_changes", to="rider.rider")),
            ],
            options={
                "verbose_name": "Historie změny čipu",
                "verbose_name_plural": "Historie změn čipů",
                "ordering": ["-changed_at"],
            },
        ),
        migrations.AddIndex(
            model_name="ridertransponderchange",
            index=models.Index(fields=["rider", "slot", "changed_at"], name="rider_chip_hist_date"),
        ),
    ]
