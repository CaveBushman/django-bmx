import logging

from django.db import migrations, models
from django.db.models import F, Q


audit_logger = logging.getLogger("audit")


def clear_duplicate_commissar_roles(apps, schema_editor):
    Event = apps.get_model("event", "Event")

    duplicate_pcp_assist_events = Event.objects.filter(
        pcp_id=F("pcp_assist_id"),
        pcp__isnull=False,
    )
    for event in duplicate_pcp_assist_events.iterator():
        old_value = event.pcp_assist_id
        event.pcp_assist_id = None
        event.save(update_fields=["pcp_assist"])
        audit_logger.warning(
            "event_commissar_constraint_cleanup event_id=%s field=pcp_assist old=%s new=%s reason=matched_pcp_during_migration",
            event.id,
            old_value,
            None,
        )

    duplicate_pcp_start_events = Event.objects.filter(
        pcp_id=F("start_commissar_id"),
        pcp__isnull=False,
    )
    for event in duplicate_pcp_start_events.iterator():
        old_value = event.start_commissar_id
        event.start_commissar_id = None
        event.save(update_fields=["start_commissar"])
        audit_logger.warning(
            "event_commissar_constraint_cleanup event_id=%s field=start_commissar old=%s new=%s reason=matched_pcp_during_migration",
            event.id,
            old_value,
            None,
        )

    duplicate_assist_start_events = Event.objects.filter(
        pcp_assist_id=F("start_commissar_id"),
        pcp_assist__isnull=False,
    )
    for event in duplicate_assist_start_events.iterator():
        old_value = event.start_commissar_id
        event.start_commissar_id = None
        event.save(update_fields=["start_commissar"])
        audit_logger.warning(
            "event_commissar_constraint_cleanup event_id=%s field=start_commissar old=%s new=%s reason=matched_pcp_assist_during_migration",
            event.id,
            old_value,
            None,
        )


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0076_event_uci_export_codes"),
    ]

    operations = [
        migrations.RunPython(clear_duplicate_commissar_roles, noop_reverse),
        migrations.AddConstraint(
            model_name="event",
            constraint=models.CheckConstraint(
                condition=Q(pcp__isnull=True) | Q(pcp_assist__isnull=True) | ~Q(pcp=F("pcp_assist")),
                name="event_distinct_pcp_and_pcp_assist",
            ),
        ),
        migrations.AddConstraint(
            model_name="event",
            constraint=models.CheckConstraint(
                condition=Q(pcp__isnull=True) | Q(start_commissar__isnull=True) | ~Q(pcp=F("start_commissar")),
                name="event_distinct_pcp_and_start_commissar",
            ),
        ),
        migrations.AddConstraint(
            model_name="event",
            constraint=models.CheckConstraint(
                condition=Q(pcp_assist__isnull=True) | Q(start_commissar__isnull=True) | ~Q(pcp_assist=F("start_commissar")),
                name="event_distinct_pcp_assist_and_start_commissar",
            ),
        ),
    ]
