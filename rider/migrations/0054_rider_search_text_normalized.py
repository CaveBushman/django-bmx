from django.db import migrations, models
import unicodedata


def normalize_search_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    without_diacritics = "".join(
        char for char in text if not unicodedata.combining(char)
    )
    return " ".join(without_diacritics.lower().split())


def populate_rider_search_text(apps, schema_editor):
    Rider = apps.get_model("rider", "Rider")
    for rider in Rider.objects.all().only(
        "id",
        "first_name",
        "middle_name",
        "last_name",
        "email",
        "uci_id",
        "transponder_20",
        "transponder_24",
        "plate_text",
    ):
        rider.search_text_normalized = normalize_search_text(
            " ".join(
                str(part) for part in [
                    rider.first_name,
                    rider.middle_name,
                    rider.last_name,
                    rider.email,
                    rider.uci_id,
                    rider.transponder_20,
                    rider.transponder_24,
                    rider.plate_text,
                ] if part
            )
        )
        rider.save(update_fields=["search_text_normalized"])


class Migration(migrations.Migration):

    dependencies = [
        ("rider", "0053_alter_riderstatscharge_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="rider",
            name="search_text_normalized",
            field=models.CharField(blank=True, db_index=True, default="", max_length=512),
        ),
        migrations.RunPython(populate_rider_search_text, migrations.RunPython.noop),
    ]
