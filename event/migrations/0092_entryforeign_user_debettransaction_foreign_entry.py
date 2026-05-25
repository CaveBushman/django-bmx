from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0091_eventphoto"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="entryforeign",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text="Uživatel, který přihlášku vytvořil přes app (kreditní platba)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="foreign_entries_created",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="debettransaction",
            name="foreign_entry",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="debet_transactions",
                to="event.entryforeign",
            ),
        ),
    ]
