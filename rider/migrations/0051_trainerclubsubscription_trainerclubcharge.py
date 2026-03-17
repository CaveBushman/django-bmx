from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_account_is_trainer_account_trainer_clubs"),
        ("event", "0071_seasonsettings_trainer_prices"),
        ("rider", "0050_ridertransponderchange"),
    ]

    operations = [
        migrations.CreateModel(
            name="TrainerClubSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product", models.CharField(choices=[("club_stats", "Prémiové statistiky klubu"), ("club_extended", "Rozšířené funkce trenéra")], db_index=True, default="club_stats", max_length=30)),
                ("starts_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("status", models.CharField(choices=[("active", "Aktivní"), ("expired", "Expirované"), ("canceled", "Zrušené"), ("past_due", "Neprodloužené")], db_index=True, default="active", max_length=20)),
                ("monthly_price", models.IntegerField(default=0)),
                ("auto_renew", models.BooleanField(default=True)),
                ("last_renewed_at", models.DateTimeField(blank=True, null=True)),
                ("canceled_at", models.DateTimeField(blank=True, null=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("club", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trainer_subscriptions", to="club.club")),
                ("season", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="trainer_club_subscriptions", to="event.seasonsettings")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trainer_club_subscriptions", to="accounts.account")),
            ],
            options={
                "verbose_name": "Předplatné trenéra pro klub",
                "verbose_name_plural": "Předplatná trenérů pro kluby",
            },
        ),
        migrations.CreateModel(
            name="TrainerClubCharge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product", models.CharField(choices=[("club_stats", "Prémiové statistiky klubu"), ("club_extended", "Rozšířené funkce trenéra")], default="club_stats", max_length=30)),
                ("amount", models.IntegerField(default=0)),
                ("period_start", models.DateTimeField()),
                ("period_end", models.DateTimeField()),
                ("reason", models.CharField(choices=[("initial", "První aktivace"), ("renewal", "Obnovení")], default="initial", max_length=20)),
                ("payment_valid", models.BooleanField(default=True)),
                ("transaction_date", models.DateTimeField(auto_now_add=True, null=True)),
                ("club", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trainer_charges", to="club.club")),
                ("season", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="trainer_club_charges", to="event.seasonsettings")),
                ("subscription", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="charges", to="rider.trainerclubsubscription")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trainer_club_charges", to="accounts.account")),
            ],
            options={
                "verbose_name": "Odečet za trenérské předplatné",
                "verbose_name_plural": "Odečty za trenérská předplatná",
            },
        ),
        migrations.AddIndex(
            model_name="trainerclubsubscription",
            index=models.Index(fields=["user", "product", "status", "expires_at"], name="trainer_sub_user_prod_exp"),
        ),
        migrations.AddIndex(
            model_name="trainerclubsubscription",
            index=models.Index(fields=["club", "product", "status", "expires_at"], name="trainer_sub_club_prod_exp"),
        ),
        migrations.AddConstraint(
            model_name="trainerclubsubscription",
            constraint=models.UniqueConstraint(condition=Q(status="active"), fields=("user", "club", "product"), name="uniq_active_trainer_club_subscription"),
        ),
        migrations.AddIndex(
            model_name="trainerclubcharge",
            index=models.Index(fields=["user", "payment_valid", "transaction_date"], name="trainer_charge_user_valid_date"),
        ),
        migrations.AddIndex(
            model_name="trainerclubcharge",
            index=models.Index(fields=["subscription"], name="trainer_charge_subscription"),
        ),
    ]
