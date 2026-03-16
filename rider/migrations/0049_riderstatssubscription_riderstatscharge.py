from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_rename_user_credit_account_credit"),
        ("event", "0064_seasonsettings_rider_stats_monthly_price"),
        ("rider", "0048_remove_rider_have_girl_bonus"),
    ]

    operations = [
        migrations.CreateModel(
            name="RiderStatsSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("starts_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("status", models.CharField(choices=[("active", "Aktivní"), ("expired", "Expirované"), ("canceled", "Zrušené"), ("past_due", "Neprodloužené")], db_index=True, default="active", max_length=20)),
                ("monthly_price", models.IntegerField(default=0)),
                ("auto_renew", models.BooleanField(default=True)),
                ("last_renewed_at", models.DateTimeField(blank=True, null=True)),
                ("canceled_at", models.DateTimeField(blank=True, null=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("rider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="premium_subscriptions", to="rider.rider")),
                ("season", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rider_stats_subscriptions", to="event.seasonsettings")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rider_stats_subscriptions", to="accounts.account")),
            ],
            options={
                "verbose_name": "Předplatné prémiových statistik",
                "verbose_name_plural": "Předplatná prémiových statistik",
            },
        ),
        migrations.CreateModel(
            name="RiderStatsCharge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.IntegerField(default=0)),
                ("period_start", models.DateTimeField()),
                ("period_end", models.DateTimeField()),
                ("reason", models.CharField(choices=[("initial", "První aktivace"), ("renewal", "Obnovení")], default="initial", max_length=20)),
                ("payment_valid", models.BooleanField(default=True)),
                ("transaction_date", models.DateTimeField(auto_now_add=True, null=True)),
                ("rider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="premium_charges", to="rider.rider")),
                ("season", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rider_stats_charges", to="event.seasonsettings")),
                ("subscription", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="charges", to="rider.riderstatssubscription")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rider_stats_charges", to="accounts.account")),
            ],
            options={
                "verbose_name": "Odečet za prémiové statistiky",
                "verbose_name_plural": "Odečty za prémiové statistiky",
            },
        ),
        migrations.AddIndex(
            model_name="riderstatssubscription",
            index=models.Index(fields=["user", "status", "expires_at"], name="rider_sub_user_status_exp"),
        ),
        migrations.AddIndex(
            model_name="riderstatssubscription",
            index=models.Index(fields=["rider", "status", "expires_at"], name="rider_sub_rider_status_exp"),
        ),
        migrations.AddConstraint(
            model_name="riderstatssubscription",
            constraint=models.UniqueConstraint(condition=Q(status="active"), fields=("user", "rider"), name="uniq_active_rider_stats_subscription"),
        ),
        migrations.AddIndex(
            model_name="riderstatscharge",
            index=models.Index(fields=["user", "payment_valid", "transaction_date"], name="rider_charge_user_valid_date"),
        ),
        migrations.AddIndex(
            model_name="riderstatscharge",
            index=models.Index(fields=["subscription"], name="rider_charge_subscription"),
        ),
    ]
