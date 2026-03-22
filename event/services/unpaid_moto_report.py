from dataclasses import dataclass

from event.models import Entry, EntryForeign, Event, RaceRun
from rider.plates import normalize_plate_value


def _normalize_text(value):
    return " ".join((value or "").strip().split())


def _normalize_name(first_name, last_name):
    return f"{_normalize_text(first_name)} {_normalize_text(last_name)}".strip().upper()


def _normalize_category(value):
    return _normalize_text(value).upper()


def _normalize_uci_id(value):
    normalized = _normalize_text(str(value or ""))
    return normalized.upper()


def _entry_category(entry):
    if getattr(entry, "is_beginner", False):
        return getattr(entry, "class_beginner", "") or ""
    if getattr(entry, "is_20", False):
        return getattr(entry, "class_20", "") or ""
    if getattr(entry, "is_24", False):
        return getattr(entry, "class_24", "") or ""
    return ""


@dataclass
class MotoUnpaidRow:
    first_name: str
    last_name: str
    uci_id: str
    plate: str
    category: str
    source: str
    reason: str


def build_unpaid_moto_report(event):
    if isinstance(event, int):
        event = Event.objects.get(pk=event)

    paid_entries = list(
        Entry.objects.filter(event=event, payment_complete=True, checkout=False).select_related("rider")
    )
    paid_foreign_entries = list(
        EntryForeign.objects.filter(event=event, payment_complete=True, checkout=False)
    )

    paid_uci_ids = set()
    paid_plate_keys = set()
    paid_name_keys = set()

    for entry in paid_entries:
        rider = entry.rider
        if rider and rider.uci_id:
            paid_uci_ids.add(_normalize_uci_id(rider.uci_id))
        category_key = _normalize_category(_entry_category(entry))
        if rider:
            plate_key = normalize_plate_value(getattr(rider, "plate_text", "") or getattr(rider, "plate", ""))
            if plate_key and category_key:
                paid_plate_keys.add((category_key, plate_key))
            name_key = _normalize_name(rider.first_name, rider.last_name)
            if name_key and category_key:
                paid_name_keys.add((category_key, name_key))

    for entry in paid_foreign_entries:
        if entry.uci_id:
            paid_uci_ids.add(_normalize_uci_id(entry.uci_id))
        category_key = _normalize_category(_entry_category(entry))
        plate_key = normalize_plate_value(entry.plate)
        if plate_key and category_key:
            paid_plate_keys.add((category_key, plate_key))
        name_key = _normalize_name(entry.first_name, entry.last_name)
        if name_key and category_key:
            paid_name_keys.add((category_key, name_key))

    runs = (
        RaceRun.objects.filter(event=event, round_type="MOTO")
        .select_related("rider", "result")
        .order_by("category", "plate", "id")
    )

    confirmed_unpaid = []
    missing_uci = []
    seen_participants = set()

    for run in runs:
        rider = run.rider
        result = run.result
        uci_id = ""
        first_name = ""
        last_name = ""

        if rider and rider.uci_id:
            uci_id = _normalize_text(str(rider.uci_id))
            first_name = rider.first_name or ""
            last_name = rider.last_name or ""
        elif result and result.rider_id:
            uci_id = _normalize_text(str(result.rider_id or ""))
            first_name = result.first_name or ""
            last_name = result.last_name or ""
        elif result:
            first_name = result.first_name or ""
            last_name = result.last_name or ""

        category = run.category or ""
        plate = run.plate or ""
        category_key = _normalize_category(category)
        plate_key = normalize_plate_value(plate)
        name_key = _normalize_name(first_name, last_name)

        participant_key = (
            uci_id.upper(),
            category_key,
            plate_key,
            name_key,
        )
        if participant_key in seen_participants:
            continue
        seen_participants.add(participant_key)

        if uci_id:
            if _normalize_uci_id(uci_id) in paid_uci_ids:
                continue
            confirmed_unpaid.append(
                MotoUnpaidRow(
                    first_name=first_name,
                    last_name=last_name,
                    uci_id=uci_id,
                    plate=plate,
                    category=category,
                    source="RaceRun / MOTO",
                    reason="Nenalezena uhrazená online registrace podle UCI ID.",
                )
            )
            continue

        matched_by_plate = bool(category_key and plate_key and (category_key, plate_key) in paid_plate_keys)
        matched_by_name = bool(category_key and name_key and (category_key, name_key) in paid_name_keys)
        if matched_by_plate or matched_by_name:
            continue

        missing_uci.append(
            MotoUnpaidRow(
                first_name=first_name,
                last_name=last_name,
                uci_id="",
                plate=plate,
                category=category,
                source="RaceRun / MOTO",
                reason="Chybí UCI ID a zároveň nebyla nalezena online registrace podle jména ani startovního čísla.",
            )
        )

    return {
        "confirmed_unpaid": confirmed_unpaid,
        "missing_uci": missing_uci,
        "flagged_count": len(confirmed_unpaid) + len(missing_uci),
        "moto_riders_count": len(seen_participants),
        "paid_entries_count": len(paid_entries) + len(paid_foreign_entries),
    }
