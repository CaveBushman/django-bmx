"""Jedinečný kód závodu (UUID) pro spárování s BMX Event Control.

Existující závody dostanou kód dopočítaný v datové migraci, teprve pak se pole
přepne na ``unique`` a ``NOT NULL``.
"""

import uuid

from django.db import migrations, models


def fill_event_codes(apps, schema_editor):
    Event = apps.get_model("event", "Event")
    for event_id in Event.objects.filter(event_code__isnull=True).values_list("id", flat=True).iterator():
        Event.objects.filter(id=event_id).update(event_code=uuid.uuid4())


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0102_racerun_event_racerun_evt_round_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="event_code",
            field=models.UUIDField(
                editable=False,
                null=True,
                help_text="Jedinečný kód závodu, který se zadává do BMX Event Control.",
                verbose_name="Kód závodu",
            ),
        ),
        migrations.RunPython(fill_event_codes, noop),
        migrations.AlterField(
            model_name="event",
            name="event_code",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                help_text="Jedinečný kód závodu, který se zadává do BMX Event Control.",
                verbose_name="Kód závodu",
            ),
        ),
    ]
