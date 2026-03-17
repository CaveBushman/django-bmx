from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("club", "0011_club_billing_email"),
        ("accounts", "0007_rename_user_credit_account_credit"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="is_club_manager",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="account",
            name="club",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="managed_users", to="club.club"),
        ),
    ]
