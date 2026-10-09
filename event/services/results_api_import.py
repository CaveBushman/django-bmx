"""Příjem výsledků závodu od BIKODY (Rider Registration API v1, výsledky).

BIKODY Cloud po závodě pošle na ``POST /api/registration/v1/events/{kód}/results``
celý závod jako NewsML-G2 se SportsML 3.1 uvnitř. Z dokumentu se zapisuje
totéž, co dnes ruční nahrání souborů z REM v adminu závodu:

* **konečné výsledky** (``Result``) — přes ``GetResult``, takže body, 20"/24",
  příchozí i přepočet rankingu jdou stejnou cestou jako u REM TSV,
* **jednotlivé jízdy** (``RaceRun``) — pro prémiové statistiky: čas v cíli
  i na Hillu, dráha, fáze a kolo, pořadí v jízdě, postup a body MČR družstev
  stejně jako ``rem_tsv_import``. REM TSV čas na Hillu nenese; tady je.

Konečné pořadí se bere z bloků ``standing`` s ``classification = split`` —
pořadí **po původních kategoriích** (sloučené kategorie se boduje každá zvlášť)
s UCI ID. Starší dokument bez nich se přečte z běžných bloků a UCI ID se
dohledá z jízd.

Obojí je **úplná náhrada** dat závodu v jedné transakci: opakované odeslání
přepíše předchozí sadu, nikdy ji nezdvojí.
"""

from __future__ import annotations

import collections
import logging
import re
from dataclasses import dataclass, field

import unidecode
from defusedxml import ElementTree as SafeET
from django.db import transaction

from event.models import Event, RaceRun, Result
from event.result import GetResult
from event.services.rem_tsv_import import _mcr_club_points
from rider.models import Rider

logger = logging.getLogger(__name__)

#: Fáze BIKODY → ``RaceRun.round_type`` (stejné hodnoty jako import z REM).
ROUND_TYPES = {
    "moto": "MOTO",
    "32f": "F32",
    "16f": "F16",
    "8f": "F8",
    "qf": "F4",
    "sf": "F2",
    "final": "FINAL",
    "lcq_round1": "LCQ",
    "lcq_heat": "LCQ",
    "round_off": "ROUNDOFF",
}
#: Vyřazovací fáze od nejnižší — postup = jezdec jel i v pozdější z nich.
KNOCKOUT_ORDER = ("32f", "16f", "8f", "qf", "sf", "final")

IRM_CODES = ("DNF", "DNS", "DSQ", "REL", "REF")


class ResultsDocumentError(ValueError):
    """Dokument nejde přečíst nebo v něm nejsou výsledky — odpověď 422."""


@dataclass
class StandingRow:
    category: str
    place: int
    uci_id: str
    first_name: str
    last_name: str
    club: str


@dataclass
class HeatRow:
    stage: str
    round_no: int | None
    heat_no: int | None
    race_number: int | None
    racing_category_key: str
    racing_category: str
    participant_key: str
    category: str
    uci_id: str
    plate: str
    lane: int | None
    rank: int | None
    irm: str
    hill_time: float | None
    finish_time: float | None
    moto_points: int | None


@dataclass
class ResultsDocument:
    standings: list[StandingRow] = field(default_factory=list)
    heats: list[HeatRow] = field(default_factory=list)
    #: Kolo 20"/24" podle kategorie (název → velikost kola), z bloku kategorií.
    wheel_sizes: dict[str, int] = field(default_factory=dict)
    version: int | None = None


# --- čtení dokumentu ----------------------------------------------------------


def _tag(node) -> str:
    return node.tag.rsplit("}", 1)[-1] if isinstance(node.tag, str) else ""


def _children(node, name):
    return [child for child in node if _tag(child) == name]


def _child(node, name):
    for child in node:
        if _tag(child) == name:
            return child
    return None


def _descendants(node, name):
    return [child for child in node.iter() if _tag(child) == name]


def _properties(node) -> dict:
    """``sports-property`` přímo pod uzlem (ne z vnořených uzlů)."""
    if node is None:
        return {}
    return {
        prop.get("formal-name"): prop.get("value")
        for prop in _children(node, "sports-property")
    }


def _int(value):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _clean(value) -> str:
    return str(value or "").strip()


def _uci(value) -> str:
    """Jen skutečné UCI ID (číslice). Náhradní klíč jezdce bez licence ne."""
    value = _clean(value)
    return value if value.isdigit() else ""


def parse(body: bytes) -> ResultsDocument:
    """Přečte NewsML-G2/SportsML dokument od BIKODY.

    ``defusedxml`` — tělo přichází zvenčí a XML entity/DTD jsou známá cesta,
    jak shodit server nebo číst soubory.
    """
    try:
        root = SafeET.fromstring(body)
    except Exception as exc:  # noqa: BLE001 — ParseError i zakázané konstrukce
        raise ResultsDocumentError(f"Dokument není platné XML: {exc}") from exc

    content = root if _tag(root) == "sports-content" else next(iter(_descendants(root, "sports-content")), None)
    if content is None:
        raise ResultsDocumentError("V dokumentu chybí sports-content (SportsML).")

    doc = ResultsDocument(version=_int(root.get("version")))

    for division in _descendants(content, "tournament-division-metadata"):
        wheel = _int(_properties(division).get("wheel-size"))
        if division.get("division-name") and wheel:
            doc.wheel_sizes[division.get("division-name")] = wheel

    doc.heats = _parse_heats(content)
    doc.standings = _parse_standings(content, doc.heats)
    return doc


def _parse_heats(content) -> list[HeatRow]:
    rows = []
    for sports_event in _children(content, "sports-event"):
        metadata = _child(sports_event, "event-metadata")
        props = _properties(metadata)
        stage = _clean(props.get("stage"))
        if stage not in ROUND_TYPES:
            continue
        team = _child(sports_event, "team")
        if team is None:
            continue
        team_meta = _child(team, "team-metadata")
        racing_key = _clean(team_meta.get("team-key") if team_meta is not None else "")
        racing_name = _clean(props.get("category")) or _clean(
            team_meta.get("name") if team_meta is not None else ""
        )
        for participant in _children(team, "participant"):
            p_meta = _child(participant, "participant-metadata")
            p_props = _properties(p_meta)
            stats = _child(participant, "participant-stats")
            s_props = _properties(stats)
            irm = _clean(s_props.get("irm")).upper()
            rows.append(HeatRow(
                stage=stage,
                round_no=_int(props.get("round")),
                heat_no=_int(props.get("heat")),
                race_number=_int(props.get("race-number")),
                racing_category_key=racing_key,
                racing_category=racing_name,
                participant_key=_clean(p_meta.get("participant-key") if p_meta is not None else ""),
                category=_clean(p_props.get("home-category")) or racing_name,
                uci_id=_uci(p_props.get("uci-id")),
                plate=_clean(p_meta.get("uniform-number") if p_meta is not None else ""),
                lane=_int(s_props.get("starting-position")),
                rank=_int(stats.get("score") if stats is not None else None),
                irm=irm if irm in IRM_CODES else "",
                hill_time=_float(s_props.get("hill-seconds")),
                finish_time=_float(s_props.get("finish-seconds")),
                moto_points=_int(s_props.get("points")) if stage == "moto" else None,
            ))
    return rows


def _parse_standings(content, heats: list[HeatRow]) -> list[StandingRow]:
    standings = _children(content, "standing")
    split = [
        s for s in standings
        if _properties(_child(s, "standing-metadata")).get("classification") == "split"
    ]
    # Bez bloků SPLIT (starší BIKODY) se bere pořadí, jak se jelo, a UCI ID
    # i jméno se dohledají z jízd podle klíče jezdce.
    fallback = not split
    zdroj = split or standings
    jezdci = {row.participant_key: row for row in heats}
    jmena = _participant_names(content)

    rows = []
    for standing in zdroj:
        metadata = _child(standing, "standing-metadata")
        category = _clean(metadata.get("standing-name") if metadata is not None else "")
        for team in _children(standing, "team"):
            t_meta = _child(team, "team-metadata")
            t_props = _properties(t_meta)
            stats = _child(team, "team-stats")
            place = _int(stats.get("rank") if stats is not None else None)
            if not category or not place:
                continue
            key = _clean(t_meta.get("team-key") if t_meta is not None else "")
            first = _clean(t_props.get("first-name"))
            last = _clean(t_props.get("last-name"))
            uci_id = _uci(t_props.get("uci-id"))
            if fallback:
                uci_id = uci_id or (jezdci[key].uci_id if key in jezdci else "")
                first, last = jmena.get(key, (first, last))
            rows.append(StandingRow(
                category=category,
                place=place,
                uci_id=uci_id,
                first_name=first,
                last_name=last,
                club=_clean(t_props.get("club")),
            ))
    return rows


def _participant_names(content) -> dict:
    jmena = {}
    for p_meta in _descendants(content, "participant-metadata"):
        name = _child(p_meta, "name")
        if name is not None:
            jmena[_clean(p_meta.get("participant-key"))] = (
                _clean(name.get("first")), _clean(name.get("last")),
            )
    return jmena


# --- zápis --------------------------------------------------------------------


def _is_beginner(category: str) -> bool:
    text = unidecode.unidecode(category or "").lower()
    return bool(re.search(r"\b(prichozi|beginners?)\b", text))


def _is_20(category: str, wheel_sizes: dict) -> bool:
    wheel = wheel_sizes.get(category)
    if wheel:
        return wheel != 24
    text = unidecode.unidecode(category or "").lower()
    return not re.search(r"\b(cruiser|cruisers|24)\b", text)


def _ordinal(rank: int) -> str:
    """Pořadí v jízdě jako u REM („1st", „2nd"…) — statistiky z něj berou číslo."""
    if 10 <= rank % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix}"


def _heat_id(row: HeatRow) -> tuple:
    """Jedna jízda: číslo jízdy v programu, jinak kategorie + fáze + kolo + jízda."""
    if row.race_number:
        return ("race", row.race_number)
    return ("heat", row.racing_category_key, row.stage, row.round_no, row.heat_no)


def _heat_code(row: HeatRow) -> str:
    if row.race_number:
        return str(row.race_number)
    if row.stage == "moto":
        return f"{row.racing_category}-M{row.round_no or 0}-{row.heat_no or 0}"
    return f"{row.racing_category}-{ROUND_TYPES[row.stage]}-{row.heat_no or 0}"


def write_results(event: Event, doc: ResultsDocument) -> dict:
    """Zapíše konečné výsledky (Result). Volá se uvnitř transakce."""
    ranking_code = GetResult.ranking_code_resolve(type=event.type_for_ranking)
    stats = {"rows": len(doc.standings), "imported": 0, "skipped": 0, "errors": 0}
    Result.objects.filter(event=event).delete()
    organizer = event.organizer.team_name if event.organizer_id else ""
    rows = []
    for row in doc.standings:
        if _is_beginner(row.category):
            stats["skipped"] += 1
            continue
        try:
            rows.append(GetResult(
                event.date,
                event.id,
                event.name,
                ranking_code,
                row.uci_id,
                str(row.place),
                row.category,
                row.first_name,
                row.last_name,
                row.club,
                organizer,
                event.type_for_ranking,
            ).build_result())
        except Exception as exc:  # noqa: BLE001 — jeden řádek nesmí shodit celý závod
            stats["errors"] += 1
            logger.error("Výsledek z API se nezapsal (event_id=%s, řádek %s): %s", event.id, row, exc)

    # Hromadně: po řádku to bylo ~3 dotazy na výsledek (create + save + signál).
    # `bulk_create` signál `post_save` nespouští, proto příznak 20"/24" u jezdců
    # (`event.signals.sync_rider_categories_from_result`) doplníme dvěma dotazy.
    Result.objects.bulk_create(rows, batch_size=500)
    stats["imported"] = len(rows)
    ranked = [r for r in rows if r.rider_id and not r.is_beginner]
    uci_20 = {r.rider_id for r in ranked if r.is_20}
    uci_24 = {r.rider_id for r in ranked if not r.is_20}
    if uci_20:
        Rider.objects.filter(uci_id__in=uci_20, is_20=False).update(is_20=True)
    if uci_24:
        Rider.objects.filter(uci_id__in=uci_24, is_24=False).update(is_24=True)
    return stats


def write_runs(event: Event, doc: ResultsDocument) -> dict:
    """Zapíše jízdy (RaceRun) pro prémiové statistiky. Volá se uvnitř transakce."""
    RaceRun.objects.filter(event=event).delete()

    uci_ids = {int(row.uci_id) for row in doc.heats if row.uci_id}
    riders = {r.uci_id: r for r in Rider.objects.filter(uci_id__in=uci_ids)}
    results = {
        (r.rider_id, r.category): r
        for r in Result.objects.filter(event=event).only("id", "rider_id", "category")
    }

    # Kolik jezdců v jízdě opravdu startovalo — DNF boduje MČR družstev za
    # poslední místo (`rem_tsv_import._mcr_club_points`).
    heat_sizes = collections.Counter(
        _heat_id(row) for row in doc.heats if row.irm != "DNS"
    )
    # Nejvyšší vyřazovací fáze, kam se jezdec v kategorii dostal.
    reached: dict = {}
    for row in doc.heats:
        if row.stage in KNOCKOUT_ORDER:
            key = (row.racing_category_key, row.participant_key)
            reached[key] = max(reached.get(key, -1), KNOCKOUT_ORDER.index(row.stage))

    runs = []
    unmatched = []
    counts = collections.Counter()
    for row in doc.heats:
        rider = riders.get(int(row.uci_id)) if row.uci_id else None
        if rider is None:
            unmatched.append({"category": row.category, "plate": row.plate})
            continue
        round_type = ROUND_TYPES[row.stage]
        place = row.irm or (_ordinal(row.rank) if row.rank else "")
        nejdal = reached.get((row.racing_category_key, row.participant_key), -1)
        if row.stage == "moto":
            qualified = nejdal >= 0
        elif row.stage in KNOCKOUT_ORDER:
            qualified = nejdal > KNOCKOUT_ORDER.index(row.stage)
        else:
            qualified = None
        result = results.get((rider.uci_id, row.category))
        runs.append(RaceRun(
            result=result,
            event=event,
            rider=rider,
            category=row.category,
            is_beginner=_is_beginner(row.category),
            is_20=_is_20(row.category, doc.wheel_sizes),
            round_type=round_type,
            round_number=row.round_no if row.stage == "moto" else None,
            heat_code=_heat_code(row),
            plate=row.plate or None,
            gate=row.race_number,
            lane=row.lane,
            place=place or None,
            race_points=_mcr_club_points(round_type, place, heat_sizes[_heat_id(row)]) if place else None,
            moto_points=row.moto_points,
            qualified_to_next_round=qualified,
            hill_time=row.hill_time,
            finish_time=row.finish_time,
        ))
        counts[round_type] += 1
    RaceRun.objects.bulk_create(runs)
    return {"created": len(runs), "counts_by_round": dict(counts), "unmatched": unmatched}


def import_document(event: Event, body: bytes) -> dict:
    """Přečte a zapíše celý dokument. Bez jediného zapsaného výsledku nic nemění."""
    doc = parse(body)
    if not doc.standings:
        raise ResultsDocumentError(
            "V dokumentu nejsou konečné výsledky (standing) — nic se nezapsalo."
        )
    with transaction.atomic():
        results = write_results(event, doc)
        if not results["imported"]:
            transaction.set_rollback(True)
            raise ResultsDocumentError(
                f"Ze {results['rows']} řádků výsledků se nezapsal žádný "
                f"(přeskočeno {results['skipped']}, chyb {results['errors']}). "
                "Původní výsledky zůstaly beze změny."
            )
        runs = write_runs(event, doc)
    return {"results": results, "runs": runs, "version": doc.version}
