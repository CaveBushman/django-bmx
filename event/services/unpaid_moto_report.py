from dataclasses import dataclass

from event.models import Entry, EntryForeign, Event, RaceRun, Result
from rider.plates import normalize_plate_value


def _str_uci(value):
    return str(value).strip().upper() if value else ""


def _str_key(value):
    return str(value).strip().upper() if value else ""


@dataclass
class MotoUnpaidRow:
    first_name: str
    last_name: str
    uci_id: str
    plate: str
    category: str


def build_unpaid_moto_report(event):
    if isinstance(event, int):
        event = Event.objects.get(pk=event)

    # --- Zaplacené UCI ID ---

    paid_uci_ids = set()

    # Online registrace českých jezdců
    for uci_id in (
        Entry.objects.filter(event=event, payment_complete=True)
        .values_list("rider__uci_id", flat=True)
    ):
        s = _str_uci(uci_id)
        if s:
            paid_uci_ids.add(s)

    # Online registrace zahraničních jezdců
    for uci_id in (
        EntryForeign.objects.filter(event=event, payment_complete=True)
        .values_list("uci_id", flat=True)
    ):
        s = _str_uci(uci_id)
        if s:
            paid_uci_ids.add(s)

    paid_entries_count = (
        Entry.objects.filter(event=event, payment_complete=True).count()
        + EntryForeign.objects.filter(event=event, payment_complete=True).count()
    )

    # --- MOTO jezdci ---

    runs = (
        RaceRun.objects.filter(event=event, round_type="MOTO")
        .select_related("rider", "result")
        .order_by("category", "plate", "id")
    )
    results = Result.objects.filter(event=event)
    results_by_rider = {
        (_str_uci(result.rider_id), _str_key(result.category)): result
        for result in results
        if result.rider_id
    }
    results_by_name = {
        (
            _str_key(result.first_name),
            _str_key(result.last_name),
            _str_key(result.category),
        ): result
        for result in results
    }

    confirmed_unpaid = []
    missing_uci = []
    seen_uci = set()
    seen_no_uci = set()

    for run in runs:
        rider = run.rider
        result = run.result
        category = run.category or ""

        if result is None and rider and rider.uci_id:
            result = results_by_rider.get((_str_uci(rider.uci_id), _str_key(category)))

        if result is None and rider:
            result = results_by_name.get(
                (
                    _str_key(rider.first_name),
                    _str_key(rider.last_name),
                    _str_key(category),
                )
            )

        if result is None:
            continue

        uci_id = ""
        first_name = ""
        last_name = ""

        if rider and rider.uci_id:
            uci_id = _str_uci(rider.uci_id)
            first_name = rider.first_name or ""
            last_name = rider.last_name or ""
        elif result and result.rider_id:
            uci_id = _str_uci(result.rider_id)
            first_name = result.first_name or ""
            last_name = result.last_name or ""
        elif result:
            first_name = result.first_name or ""
            last_name = result.last_name or ""

        plate = run.plate or ""

        if uci_id:
            if uci_id in seen_uci:
                continue
            seen_uci.add(uci_id)

            if uci_id not in paid_uci_ids:
                confirmed_unpaid.append(MotoUnpaidRow(
                    first_name=first_name,
                    last_name=last_name,
                    uci_id=uci_id,
                    plate=plate,
                    category=category,
                ))
        else:
            no_uci_key = (
                normalize_plate_value(plate),
                category,
                first_name.strip().upper(),
                last_name.strip().upper(),
            )
            if no_uci_key in seen_no_uci:
                continue
            seen_no_uci.add(no_uci_key)

            missing_uci.append(MotoUnpaidRow(
                first_name=first_name,
                last_name=last_name,
                uci_id="",
                plate=plate,
                category=category,
            ))

    return {
        "confirmed_unpaid": confirmed_unpaid,
        "missing_uci": missing_uci,
        "flagged_count": len(confirmed_unpaid),
        "moto_riders_count": len(seen_uci) + len(seen_no_uci),
        "paid_entries_count": paid_entries_count,
    }
