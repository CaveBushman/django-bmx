from django.db import migrations, models
import unicodedata


def normalize_search_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    without_diacritics = "".join(
        char for char in text if not unicodedata.combining(char)
    )
    return " ".join(without_diacritics.lower().split())


def populate_account_search_text(apps, schema_editor):
    Account = apps.get_model("accounts", "Account")
    for account in Account.objects.all().only("id", "email", "username", "first_name", "last_name"):
        account.search_text_normalized = normalize_search_text(
            " ".join(
                part for part in [
                    account.email,
                    account.username,
                    account.first_name,
                    account.last_name,
                ] if part
            )
        )
        account.save(update_fields=["search_text_normalized"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_alter_avatarchangerequest_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="search_text_normalized",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
        migrations.RunPython(populate_account_search_text, migrations.RunPython.noop),
    ]
