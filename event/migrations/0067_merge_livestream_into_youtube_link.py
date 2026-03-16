from django.db import migrations


def copy_livestream_to_youtube_link(apps, schema_editor):
    Event = apps.get_model("event", "Event")
    for event in Event.objects.exclude(livestream__isnull=True).exclude(livestream=""):
        if not event.youtube_link:
            event.youtube_link = event.livestream
            event.save(update_fields=["youtube_link"])


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0066_event_uec_link"),
    ]

    operations = [
        migrations.RunPython(copy_livestream_to_youtube_link, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="event",
            name="livestream",
        ),
    ]
