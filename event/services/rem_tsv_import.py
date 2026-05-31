import csv

from django.db import transaction

from event.models import RaceRun
from rider.models import Rider


MOTO_ROUNDS = range(1, 10)
KNOCKOUT_ROUNDS = ("F128", "F64", "F32", "F16", "F8", "F4", "F2", "FINAL")
MCR_MOTO_POINTS = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
MCR_F4_POINTS = {1: 5, 2: 5, 3: 5, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
MCR_F2_POINTS = {1: 0, 2: 0, 3: 0, 4: 0, 5: 8, 6: 6, 7: 4, 8: 2}
MCR_FINAL_POINTS = {1: 22, 2: 18, 3: 15, 4: 13, 5: 12, 6: 11, 7: 10, 8: 9}


def _clean(value):
    return str(value or "").strip()


def _parse_int(value):
    value = _clean(value)
    if not value:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_float(value):
    value = _clean(value)
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _place_rank(value):
    value = _clean(value).lower()
    digits = "".join(char for char in value if char.isdigit())
    return _parse_int(digits)


def _mcr_club_points(round_type, place):
    rank = _place_rank(place)
    if rank is None:
        return None
    if round_type == "MOTO":
        return MCR_MOTO_POINTS.get(rank, 0)
    if round_type == "F4":
        return MCR_F4_POINTS.get(rank, 0)
    if round_type == "F2":
        return MCR_F2_POINTS.get(rank, 0)
    if round_type == "FINAL":
        return MCR_FINAL_POINTS.get(rank, 0)
    return _parse_int(place)


def _has_round(raw, prefix):
    return any(
        _clean(raw.get(f"{prefix}_{suffix}"))
        for suffix in ("PLACE", "TIME", "RACE_POINTS", "MOTO_POINTS", "GATE", "LANE")
    )


def _is_20_category(category):
    return "cruiser" not in _clean(category).lower()


def _has_later_round(raw, current):
    if current == "MOTO":
        later = KNOCKOUT_ROUNDS
    else:
        try:
            later = KNOCKOUT_ROUNDS[KNOCKOUT_ROUNDS.index(current) + 1:]
        except ValueError:
            later = ()
    return any(_has_round(raw, prefix) for prefix in later)


def _build_run(event, raw, rider, round_type, *, round_number=None):
    prefix = f"MOTO{round_number}" if round_type == "MOTO" else round_type
    category = _clean(raw.get("CLASS"))
    place = _clean(raw.get(f"{prefix}_PLACE"))
    return RaceRun(
        event=event,
        rider=rider,
        category=category,
        is_20=_is_20_category(category),
        round_type=round_type,
        round_number=round_number,
        heat_code=_clean(raw.get(f"{prefix}_GATE")),
        plate=_clean(raw.get("PLATE")),
        gate=_parse_int(raw.get(f"{prefix}_GATE")),
        lane=_parse_int(raw.get(f"{prefix}_LANE")),
        place=place,
        race_points=_mcr_club_points(round_type, place),
        moto_points=_parse_int(raw.get(f"{prefix}_MOTO_POINTS")),
        qualified_to_next_round=_has_later_round(raw, round_type),
        finish_time=_parse_float(raw.get(f"{prefix}_TIME")),
    )


class RemTsvRaceRunImportService:
    def import_file(self, event, path):
        with open(path, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))

        uci_ids = [_clean(row.get("UCIID")) for row in rows if _clean(row.get("UCIID"))]
        riders_by_uci = {
            str(rider.uci_id): rider
            for rider in Rider.objects.filter(uci_id__in=uci_ids)
        }

        runs = []
        unmatched = []
        for raw in rows:
            uci_id = _clean(raw.get("UCIID"))
            rider = riders_by_uci.get(uci_id)
            if rider is None:
                unmatched.append(
                    {
                        "category": _clean(raw.get("CLASS")),
                        "plate": _clean(raw.get("PLATE")),
                        "name": f"{_clean(raw.get('FIRST_NAME'))} {_clean(raw.get('LAST_NAME'))}".strip(),
                    }
                )
                continue

            for round_number in MOTO_ROUNDS:
                if _has_round(raw, f"MOTO{round_number}"):
                    runs.append(_build_run(event, raw, rider, "MOTO", round_number=round_number))
            for round_type in KNOCKOUT_ROUNDS:
                if _has_round(raw, round_type):
                    runs.append(_build_run(event, raw, rider, round_type))

        with transaction.atomic():
            RaceRun.objects.filter(event=event).delete()
            RaceRun.objects.bulk_create(runs)

        counts = {}
        for run in runs:
            counts[run.round_type] = counts.get(run.round_type, 0) + 1
        return {
            "created": len(runs),
            "counts_by_round": counts,
            "unmatched": unmatched,
        }
