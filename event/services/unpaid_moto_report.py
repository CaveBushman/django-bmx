import os
import re
from dataclasses import dataclass

from django.conf import settings

from event.models import Entry, EntryForeign, Event, RaceRun, Result
from event.services.race_run_import import _extract_tables
from rider.models import Rider
from rider.plates import normalize_plate_value


def _str_uci(value):
    return str(value).strip().upper() if value else ""


def _str_key(value):
    return " ".join(str(value or "").strip().upper().split())


def _participant_key(*, category, plate, first_name, last_name):
    return (
        _str_key(category),
        normalize_plate_value(plate),
        _str_key(first_name),
        _str_key(last_name),
    )


def _name_plate_key(*, plate, first_name, last_name):
    return (
        normalize_plate_value(plate),
        _str_key(first_name),
        _str_key(last_name),
    )


def _name_key(*, first_name, last_name):
    return (
        _str_key(first_name),
        _str_key(last_name),
    )


def _parse_full_name(value):
    cleaned = re.sub(r"\[[^\]]*\]", "", value or "")
    parts = [part for part in cleaned.strip().split() if part]
    if len(parts) < 2:
        return cleaned.strip(), ""
    return " ".join(parts[:-1]), parts[-1]


@dataclass
class MotoUnpaidRow:
    first_name: str
    last_name: str
    uci_id: str
    plate: str
    category: str


def _entry_category(entry):
    if getattr(entry, "is_beginner", False):
        return getattr(entry, "class_beginner", "") or ""
    if getattr(entry, "is_20", False):
        return getattr(entry, "class_20", "") or ""
    if getattr(entry, "is_24", False):
        return getattr(entry, "class_24", "") or ""
    return ""


def _build_paid_participant_index(event):
    paid_uci_ids = set()
    paid_participant_keys = set()
    paid_name_plate_keys = set()
    paid_name_keys = set()

    paid_entries = Entry.objects.filter(event=event, payment_complete=True).select_related("rider")
    for entry in paid_entries:
        rider = entry.rider
        if rider is None:
            continue
        uci_id = _str_uci(rider.uci_id)
        if uci_id:
            paid_uci_ids.add(uci_id)

        category = _entry_category(entry)
        plate = getattr(rider, "plate_text", "") or getattr(rider, "plate", "") or rider.plate_display
        paid_participant_keys.add(
            _participant_key(
                category=category,
                plate=plate,
                first_name=rider.first_name,
                last_name=rider.last_name,
            )
        )
        paid_name_plate_keys.add(
            _name_plate_key(
                plate=plate,
                first_name=rider.first_name,
                last_name=rider.last_name,
            )
        )
        paid_name_keys.add(_name_key(first_name=rider.first_name, last_name=rider.last_name))

    paid_foreign_entries = EntryForeign.objects.filter(event=event, payment_complete=True)
    for entry in paid_foreign_entries:
        uci_id = _str_uci(entry.uci_id)
        if uci_id:
            paid_uci_ids.add(uci_id)

        paid_participant_keys.add(
            _participant_key(
                category=_entry_category(entry),
                plate=entry.plate,
                first_name=entry.first_name,
                last_name=entry.last_name,
            )
        )
        paid_name_plate_keys.add(
            _name_plate_key(
                plate=entry.plate,
                first_name=entry.first_name,
                last_name=entry.last_name,
            )
        )
        paid_name_keys.add(_name_key(first_name=entry.first_name, last_name=entry.last_name))

    return paid_uci_ids, paid_participant_keys, paid_name_plate_keys, paid_name_keys


def _find_motos_start_file(event):
    stats_dir = os.path.join(settings.MEDIA_ROOT, "event_stats", str(event.pk))
    if not os.path.isdir(stats_dir):
        return None

    for filename in sorted(os.listdir(stats_dir)):
        if not filename.lower().endswith(".html"):
            continue
        if filename.split("__", 1)[0] == "motos":
            return os.path.join(stats_dir, filename)
    return None


def _build_event_identity_maps(event):
    results_by_name = {}
    results_by_plate = {}
    for result in Result.objects.filter(event=event):
        name_key = (
            _str_key(result.first_name),
            _str_key(result.last_name),
            _str_key(result.category),
        )
        results_by_name[name_key] = result

        rider = None
        try:
            rider = result.rider
        except Rider.DoesNotExist:
            rider = None

        if rider:
            plate = getattr(rider, "plate_text", "") or getattr(rider, "plate", "")
            if plate:
                results_by_plate[(_str_key(result.category), normalize_plate_value(plate))] = result

    riders_by_name_plate = {}
    for rider in Rider.objects.filter(is_active=True):
        plate = getattr(rider, "plate_text", "") or getattr(rider, "plate", "")
        if not plate:
            continue
        riders_by_name_plate[
            (
                _str_key(rider.first_name),
                _str_key(rider.last_name),
                normalize_plate_value(plate),
            )
        ] = rider

    return results_by_name, results_by_plate, riders_by_name_plate


def _build_report_from_motos_start_file(event, motos_file):
    paid_uci_ids, paid_participant_keys, paid_name_plate_keys, paid_name_keys = _build_paid_participant_index(event)
    results_by_name, results_by_plate, riders_by_name_plate = _build_event_identity_maps(event)

    confirmed_unpaid = []
    seen_participants = set()

    for table in _extract_tables(motos_file):
        category = table["category"]
        for row in table["rows"]:
            if len(row) < 3:
                continue

            plate = row[0]["text"]
            first_name, last_name = _parse_full_name(row[2]["text"])
            if not first_name or not last_name:
                continue
            participant_key = _participant_key(
                category=category,
                plate=plate,
                first_name=first_name,
                last_name=last_name,
            )

            if participant_key in seen_participants:
                continue
            seen_participants.add(participant_key)

            if participant_key in paid_participant_keys:
                continue
            if _name_plate_key(plate=plate, first_name=first_name, last_name=last_name) in paid_name_plate_keys:
                continue
            if _name_key(first_name=first_name, last_name=last_name) in paid_name_keys:
                continue

            result = results_by_plate.get((_str_key(category), normalize_plate_value(plate)))
            if result is None:
                result = results_by_name.get((_str_key(first_name), _str_key(last_name), _str_key(category)))

            uci_id = ""
            if result and result.rider_id:
                uci_id = _str_uci(result.rider_id)
            else:
                rider = riders_by_name_plate.get(
                    (_str_key(first_name), _str_key(last_name), normalize_plate_value(plate))
                )
                if rider and _str_uci(rider.uci_id) not in paid_uci_ids:
                    uci_id = _str_uci(rider.uci_id)

            confirmed_unpaid.append(
                MotoUnpaidRow(
                    first_name=first_name,
                    last_name=last_name,
                    uci_id=uci_id,
                    plate=plate or "",
                    category=category or "",
                )
            )

    return {
        "confirmed_unpaid": confirmed_unpaid,
        "missing_uci": [],
        "flagged_count": len(confirmed_unpaid),
        "moto_riders_count": len(seen_participants),
        "paid_entries_count": (
            Entry.objects.filter(event=event, payment_complete=True).count()
            + EntryForeign.objects.filter(event=event, payment_complete=True).count()
        ),
    }


def _build_report_from_race_runs(event):
    paid_uci_ids, _, _, _ = _build_paid_participant_index(event)
    results_by_name, results_by_plate, _ = _build_event_identity_maps(event)
    runs = (
        RaceRun.objects.filter(event=event, round_type="MOTO")
        .select_related("rider", "result")
        .order_by("category", "plate", "id")
    )

    confirmed_unpaid = []
    missing_uci = []
    seen_uci = set()
    seen_no_uci = set()

    for run in runs:
        rider = run.rider
        result = run.result
        category = run.category or ""

        if result is None and rider:
            plate = getattr(rider, "plate_text", "") or getattr(rider, "plate", "")
            if plate:
                result = results_by_plate.get((_str_key(category), normalize_plate_value(plate)))
            if result is None:
                result = results_by_name.get(
                    (_str_key(rider.first_name), _str_key(rider.last_name), _str_key(category))
                )

        if result is None:
            continue

        uci_id = ""
        first_name = ""
        last_name = ""

        if result and result.rider_id:
            uci_id = _str_uci(result.rider_id)
            first_name = result.first_name or ""
            last_name = result.last_name or ""
        elif rider and rider.uci_id:
            uci_id = _str_uci(rider.uci_id)
            first_name = rider.first_name or ""
            last_name = rider.last_name or ""
        elif result:
            first_name = result.first_name or ""
            last_name = result.last_name or ""

        plate = run.plate or ""

        if uci_id:
            if uci_id in seen_uci:
                continue
            seen_uci.add(uci_id)
            if uci_id not in paid_uci_ids:
                confirmed_unpaid.append(
                    MotoUnpaidRow(
                        first_name=first_name,
                        last_name=last_name,
                        uci_id=uci_id,
                        plate=plate,
                        category=category,
                    )
                )
        else:
            no_uci_key = _participant_key(
                category=category,
                plate=plate,
                first_name=first_name,
                last_name=last_name,
            )
            if no_uci_key in seen_no_uci:
                continue
            seen_no_uci.add(no_uci_key)
            missing_uci.append(
                MotoUnpaidRow(
                    first_name=first_name,
                    last_name=last_name,
                    uci_id="",
                    plate=plate,
                    category=category,
                )
            )

    return {
        "confirmed_unpaid": confirmed_unpaid,
        "missing_uci": missing_uci,
        "flagged_count": len(confirmed_unpaid),
        "moto_riders_count": len(seen_uci) + len(seen_no_uci),
        "paid_entries_count": (
            Entry.objects.filter(event=event, payment_complete=True).count()
            + EntryForeign.objects.filter(event=event, payment_complete=True).count()
        ),
    }


def build_unpaid_moto_report(event):
    if isinstance(event, int):
        event = Event.objects.get(pk=event)

    motos_file = _find_motos_start_file(event)
    if motos_file:
        return _build_report_from_motos_start_file(event, motos_file)

    return _build_report_from_race_runs(event)
