# Generated by Django 5.0.3 on 2025-02-18 09:39

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_rename_credit_account_user_credit"),
    ]

    operations = [
        migrations.RenameField(
            model_name="account", old_name="user_credit", new_name="credit",
        ),
    ]
