from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0080_normalize_entryforeign_uci_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="reg_cancel_to",
            field=models.DateTimeField(
                blank=True,
                help_text="Termín do kdy je možné odhlášení. Pokud není vyplněn, použije se konec registrace.",
                null=True,
            ),
        ),
    ]
