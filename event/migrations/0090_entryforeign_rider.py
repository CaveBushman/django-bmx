from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0089_event_eshop_pickup_details"),
        ("rider", "0054_rider_search_text_normalized"),
    ]

    operations = [
        migrations.AddField(
            model_name="entryforeign",
            name="rider",
            field=models.ForeignKey(
                blank=True,
                help_text="Propojení s českým jezdcem (pokud jezdec závodí pod zahraniční licencí)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="foreign_entries",
                to="rider.rider",
            ),
        ),
    ]
