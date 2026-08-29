import collections
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
MCR_POINTS_TABLES = {
    "MOTO": MCR_MOTO_POINTS,
    "F4": MCR_F4_POINTS,
    "F2": MCR_F2_POINTS,
    "FINAL": MCR_FINAL_POINTS,
}
# Prefixy sloupců všech kol, která REM v exportu posílá.
ROUND_PREFIXES = tuple(f"MOTO{number}" for number in MOTO_ROUNDS) + KNOCKOUT_ROUNDS
# Stavy místo pořadí. DNF se boduje za poslední místo v jízdě, zbytek je bez bodu.
PLACE_TOKENS = ("DNF", "DNS", "REL", "DSQ", "NP")


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


def _place_token(value):
    """Vrátí stav jízdy (DNF, DNS, REL, DSQ, NP), pokud místo pořadí došel stav."""
    text = _clean(value).upper()
    for token in PLACE_TOKENS:
        if text.startswith(token):
            return token
    return None


def _mcr_club_points(round_type, place, heat_size=None):
    """Body družstvu za jednu jízdu.

    Stav se musí rozpoznat dřív, než se ze zápisu tahá číslice: "REL+2" nese
    velikost penalizace, ne pořadí, takže se z něj dosud počítalo druhé místo
    a relegovaný jezdec vozil týmu sedm bodů.

    DNF dostane body za poslední místo v jízdě — při sedmi jezdcích za sedmé,
    při pěti za páté. Kolik jich v jízdě bylo, ví jen ``heat_size``; bez něj
    zůstane jízda nebodovaná, ať se nehádá.
    """
    table = MCR_POINTS_TABLES.get(round_type)
    token = _place_token(place)
    if token == "DNF":
        if table is None or not heat_size:
            return None
        return table.get(heat_size, 0)
    if token:
        return 0
    rank = _place_rank(place)
    if rank is None:
        return None
    if table is None:
        return _parse_int(place)
    return table.get(rank, 0)


def _heat_sizes(rows):
    """Počet jezdců v každé jízdě, klíč ``(prefix kola, číslo jízdy)``.

    Poslední místo nejde odvodit z jednoho řádku — DNF jezdec musí vědět,
    kolik jich s ním stálo na brance. Číslo jízdy je v exportu ve sloupci
    ``*_GATE`` (``*_LANE`` je pozice na brance) a mezi třídami se nesdílí.
    Nestartující se nepočítají: v jízdě nebyli, takže neposouvají poslední
    místo směrem dolů.
    """
    sizes = collections.Counter()
    for raw in rows:
        for prefix in ROUND_PREFIXES:
            gate = _clean(raw.get(f"{prefix}_GATE"))
            place = _clean(raw.get(f"{prefix}_PLACE"))
            if gate and place and _place_token(place) != "DNS":
                sizes[(prefix, gate)] += 1
    return sizes


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


def _build_run(event, raw, rider, round_type, *, round_number=None, heat_sizes=None):
    prefix = f"MOTO{round_number}" if round_type == "MOTO" else round_type
    category = _clean(raw.get("CLASS"))
    place = _clean(raw.get(f"{prefix}_PLACE"))
    heat_size = (heat_sizes or {}).get((prefix, _clean(raw.get(f"{prefix}_GATE"))))
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
        race_points=_mcr_club_points(round_type, place, heat_size),
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

        heat_sizes = _heat_sizes(rows)
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
                    runs.append(
                        _build_run(event, raw, rider, "MOTO", round_number=round_number, heat_sizes=heat_sizes)
                    )
            for round_type in KNOCKOUT_ROUNDS:
                if _has_round(raw, round_type):
                    runs.append(_build_run(event, raw, rider, round_type, heat_sizes=heat_sizes))

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
