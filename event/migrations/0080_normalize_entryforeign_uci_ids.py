from django.db import migrations


def normalize_entryforeign_uci_ids(apps, schema_editor):
    EntryForeign = apps.get_model("event", "EntryForeign")

    for entry in EntryForeign.objects.all().only("id", "uci_id"):
        normalized_uci_id = "".join(ch for ch in str(entry.uci_id or "") if ch.isdigit())
        if normalized_uci_id == (entry.uci_id or ""):
            continue
        entry.uci_id = normalized_uci_id
        entry.save(update_fields=["uci_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0079_eventproposition_ckeditor5"),
    ]

    operations = [
        migrations.RunPython(normalize_entryforeign_uci_ids, migrations.RunPython.noop),
    ]
