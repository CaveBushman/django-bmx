"""Synchronizace jezdců a klubů s centrální databází Event Control Admin.

Směry:

* **výdej (push)** — Event Control Admin si přes API čte jezdce a kluby z webu.
  Web je master dat, proto se vydávají kompletní záznamy včetně tabulky, čipu,
  třídy a platnosti licence. Přírůstkově přes ``updated_since``.
* **stahování (pull)** — jezdci a kluby zakládané centrálně. Protože master je
  web, stahování **nikdy nepřepisuje** existující lokální data: doplní jen
  párovací ``event_control_id``, rozdíly zapíše do logu jako konflikty a
  neznámé záznamy založí (jezdce jako neschválené, ať projdou běžným schválením).

Remote formát je držený úmyslně tolerantně (``id``/``uci_id``/``sex``/``gender``…),
aby stačilo doladit mapování, až bude centrální API hotové.
"""

import logging
from datetime import date, datetime

import requests
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from club.models import Club
from event.models_sync import EventControlSyncLog
from rider.models import Rider

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")

MAX_PAGE_SIZE = 2000
DEFAULT_PAGE_SIZE = 500


# ---------------------------------------------------------------------------
# Výdej master dat (Event Control Admin → čte z webu)
# ---------------------------------------------------------------------------

def _sex(gender) -> str:
    return "f" if gender == "Žena" else "m"


def _iso(value):
    return value.isoformat() if value else None


def rider_payload(rider) -> dict:
    return {
        "event_control_id": rider.event_control_id or "",
        "uci_id": str(rider.uci_id),
        "first_name": rider.first_name or "",
        "middle_name": rider.middle_name or "",
        "last_name": rider.last_name or "",
        "sex": _sex(rider.gender),
        "gender": rider.gender or "",
        "date_of_birth": _iso(rider.date_of_birth),
        "nationality": rider.nationality or "",
        "email": rider.email or "",
        "club": rider.club.team_name if rider.club_id else "",
        "club_id": rider.club_id,
        "club_event_control_id": rider.club.event_control_id if rider.club_id else "",
        "is_elite": rider.is_elite,
        "class_20": rider.class_20 or "",
        "class_24": rider.class_24 or "",
        "class_beginner": rider.class_beginner or "",
        "plate": rider.plate_display or "",
        "plate_champ_20": rider.plate_champ_20,
        "plate_champ_24": rider.plate_champ_24,
        "transponder_20": rider.transponder_20 or "",
        "transponder_24": rider.transponder_24 or "",
        "valid_licence": rider.valid_licence,
        "is_active": rider.is_active,
        "is_approved": rider.is_approved,
        "updated": _iso(rider.updated),
    }


def club_payload(club) -> dict:
    return {
        "event_control_id": club.event_control_id or "",
        "id": club.id,
        "team_name": club.team_name or "",
        "club_name": club.club_name or "",
        "ico": club.ico or "",
        "city": club.city or "",
        "region": club.region or "",
        "country": "CZE",
        "web": club.web or "",
        "contact_email": club.contact_email or "",
        "is_active": club.is_active,
        "updated": _iso(club.updated),
    }


def paginate(queryset, payload_builder, limit, offset):
    limit = max(1, min(limit or DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE))
    offset = max(0, offset or 0)
    total = queryset.count()
    rows = list(queryset[offset:offset + limit])
    next_offset = offset + len(rows)
    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset if next_offset < total else None,
        "generated_at": timezone.now().isoformat(),
        "results": [payload_builder(row) for row in rows],
    }


def riders_queryset(updated_since=None, include_inactive=False):
    """Jezdci k výdeji, seřazení podle ``updated``.

    Řazení je součást kontraktu, ne úklid: konzument stránkuje přírůstkově
    a záznam upravený uprostřed importu by se při jiném řazení mohl mezi
    stránkami přesunout tak, že ho konzument nikdy neuvidí.
    """
    queryset = Rider.objects.select_related("club").all()
    if not include_inactive:
        queryset = queryset.filter(is_active=True, is_approved=True)
    if updated_since:
        queryset = queryset.filter(updated__gte=updated_since)
    return queryset.order_by("updated", "id")


def clubs_queryset(updated_since=None, include_inactive=False):
    """Kluby k výdeji, seřazené podle ``updated`` — viz `riders_queryset`."""
    queryset = Club.objects.all()
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    if updated_since:
        queryset = queryset.filter(updated__gte=updated_since)
    return queryset.order_by("updated", "id")


def riders_page(updated_since=None, limit=DEFAULT_PAGE_SIZE, offset=0, include_inactive=False) -> dict:
    """Přírůstkový výdej jezdců pro centrální databázi."""
    return paginate(
        riders_queryset(updated_since, include_inactive), rider_payload, limit, offset
    )


def clubs_page(updated_since=None, limit=DEFAULT_PAGE_SIZE, offset=0, include_inactive=False) -> dict:
    """Přírůstkový výdej klubů pro centrální databázi."""
    return paginate(
        clubs_queryset(updated_since, include_inactive), club_payload, limit, offset
    )


# ---------------------------------------------------------------------------
# Stahování centrálně založených záznamů (web → čte z Event Control Admin)
# ---------------------------------------------------------------------------

class EventControlAdminUnavailable(RuntimeError):
    """Centrální API není nakonfigurované nebo neodpovědělo."""


class EventControlAdminClient:
    """Minimalistický HTTP klient centrálního API (HTTP Basic)."""

    def __init__(self, base_url=None, username=None, password=None, timeout=None):
        self.base_url = (base_url or getattr(settings, "EVENT_CONTROL_ADMIN_URL", "") or "").rstrip("/")
        self.username = username or getattr(settings, "EVENT_CONTROL_ADMIN_USERNAME", "")
        self.password = password or getattr(settings, "EVENT_CONTROL_ADMIN_PASSWORD", "")
        self.timeout = timeout or getattr(settings, "EVENT_CONTROL_ADMIN_TIMEOUT", 30)

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def fetch(self, entity: str, updated_since=None) -> list:
        """Stáhne všechny stránky dané entity (``riders`` / ``clubs``)."""
        if not self.configured:
            raise EventControlAdminUnavailable(
                "EVENT_CONTROL_ADMIN_URL není nastavené — synchronizace je vypnutá."
            )

        url = f"{self.base_url}/{entity}/"
        params = {"limit": getattr(settings, "EVENT_CONTROL_ADMIN_PAGE_SIZE", DEFAULT_PAGE_SIZE)}
        if updated_since:
            params["updated_since"] = updated_since.isoformat() if hasattr(updated_since, "isoformat") else updated_since

        auth = (self.username, self.password) if self.username else None
        records = []
        offset = 0
        while True:
            page_params = dict(params, offset=offset)
            try:
                response = requests.get(url, params=page_params, auth=auth, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError) as error:
                raise EventControlAdminUnavailable(f"Chyba komunikace s {url}: {error}") from error

            page, next_offset = self._read_page(data)
            records.extend(page)
            if not page or next_offset is None:
                break
            offset = next_offset
        return records

    @staticmethod
    def _read_page(data):
        """Přijme jak ``{"results": [...], "next_offset": n}``, tak čisté pole."""
        if isinstance(data, list):
            return data, None
        if not isinstance(data, dict):
            return [], None
        page = data.get("results") or data.get("data") or data.get("items") or []
        return page, data.get("next_offset")


def _remote_value(record, *keys, default=""):
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return default


def _remote_gender(record):
    raw = str(_remote_value(record, "gender", "sex", "rider_sex")).strip().lower()
    if raw in {"f", "female", "žena", "zena", "w"}:
        return "Žena"
    if raw in {"m", "male", "muž", "muz"}:
        return "Muž"
    return "Ostatní" if raw else ""


def _remote_date(record, *keys):
    raw = _remote_value(record, *keys, default=None)
    if raw in (None, ""):
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    parsed = parse_date(str(raw)[:10])
    if parsed is None:
        parsed_dt = parse_datetime(str(raw))
        parsed = parsed_dt.date() if parsed_dt else None
    return parsed


def _remote_uci_id(record):
    raw = _remote_value(record, "uci_id", "uciid", "rider_uciid", default="")
    digits = "".join(char for char in str(raw) if char.isdigit())
    return int(digits) if digits else None


def _differences(instance, record_values):
    """Pole, kde se centrální data liší od lokálních (web má přednost)."""
    diffs = {}
    for field, remote in record_values.items():
        if remote in (None, ""):
            continue
        local = getattr(instance, field, None)
        if isinstance(local, date) and isinstance(remote, date):
            equal = local == remote
        else:
            equal = str(local or "").strip().casefold() == str(remote).strip().casefold()
        if not equal:
            diffs[field] = {"local": str(local or ""), "remote": str(remote)}
    return diffs


def _match_club(record):
    external_id = str(_remote_value(record, "event_control_id", "id", default="")).strip()
    if external_id:
        club = Club.objects.filter(event_control_id=external_id).first()
        if club:
            return club, external_id
    ico = str(_remote_value(record, "ico", "company_id", default="")).strip()
    if ico:
        club = Club.objects.filter(ico=ico).first()
        if club:
            return club, external_id
    name = str(_remote_value(record, "team_name", "name", "club", default="")).strip()
    if name:
        club = Club.objects.filter(Q(team_name__iexact=name) | Q(club_name__iexact=name)).first()
        if club:
            return club, external_id
    return None, external_id


def sync_clubs(records, *, source="command", dry_run=False) -> EventControlSyncLog:
    """Spáruje (a případně založí) kluby z centrální databáze."""
    log = EventControlSyncLog.objects.create(
        direction=EventControlSyncLog.Direction.PULL,
        entity=EventControlSyncLog.Entity.CLUBS,
        source=source,
        dry_run=dry_run,
        received=len(records),
    )
    conflicts, created_names, skipped = {}, [], []

    for record in records:
        name = str(_remote_value(record, "team_name", "name", "club", default="")).strip()
        club, external_id = _match_club(record)
        remote_values = {
            "team_name": name,
            "ico": str(_remote_value(record, "ico", "company_id", default="")).strip(),
            "city": str(_remote_value(record, "city", "town", default="")).strip(),
        }

        if club is not None:
            diffs = _differences(club, remote_values)
            if diffs:
                conflicts[club.team_name] = diffs
                log.conflicts += 1
            log.matched += 1
            if not dry_run:
                club.event_control_id = external_id or club.event_control_id
                club.event_control_synced = timezone.now()
                club.save(update_fields=["event_control_id", "event_control_synced", "updated"])
            continue

        if not name:
            skipped.append(record)
            log.skipped += 1
            continue

        log.created += 1
        created_names.append(name)
        if not dry_run:
            Club.objects.create(
                team_name=name,
                club_name=str(_remote_value(record, "club_name", default="")).strip(),
                ico=remote_values["ico"][:8],
                city=remote_values["city"][:100],
                event_control_id=external_id,
                event_control_synced=timezone.now(),
            )

    log.detail = {"conflicts": conflicts, "created": created_names, "skipped": skipped[:20]}
    log.succeeded = True
    log.finished = timezone.now()
    log.save()
    audit_logger.info(
        "event_control_sync_clubs source=%s received=%s matched=%s created=%s conflicts=%s dry_run=%s",
        source, log.received, log.matched, log.created, log.conflicts, dry_run,
    )
    return log


def _match_rider(record):
    external_id = str(_remote_value(record, "event_control_id", "id", default="")).strip()
    if external_id:
        rider = Rider.objects.filter(event_control_id=external_id).first()
        if rider:
            return rider, external_id
    uci_id = _remote_uci_id(record)
    if uci_id:
        rider = Rider.objects.filter(uci_id=uci_id).first()
        if rider:
            return rider, external_id
    return None, external_id


def _resolve_rider_club(record):
    club_id = str(_remote_value(record, "club_event_control_id", "club_id", default="")).strip()
    if club_id:
        club = Club.objects.filter(event_control_id=club_id).first()
        if club:
            return club
    name = str(_remote_value(record, "club", "club_name", "team_name", default="")).strip()
    if name:
        return Club.objects.filter(Q(team_name__iexact=name) | Q(club_name__iexact=name)).first()
    return None


def sync_riders(records, *, source="command", dry_run=False) -> EventControlSyncLog:
    """Spáruje (a případně založí) jezdce z centrální databáze.

    Lokální data se nepřepisují — web je master. Nově založení jezdci zůstávají
    neschválení (``is_approved=False``), ať projdou standardním schválením.
    """
    log = EventControlSyncLog.objects.create(
        direction=EventControlSyncLog.Direction.PULL,
        entity=EventControlSyncLog.Entity.RIDERS,
        source=source,
        dry_run=dry_run,
        received=len(records),
    )
    conflicts, created_riders, skipped = {}, [], []

    for record in records:
        rider, external_id = _match_rider(record)
        uci_id = _remote_uci_id(record)
        remote_values = {
            "first_name": str(_remote_value(record, "first_name", "rider_first", default="")).strip(),
            "last_name": str(_remote_value(record, "last_name", "rider_last", default="")).strip(),
            "date_of_birth": _remote_date(record, "date_of_birth", "birthdate", "rider_birthdate"),
            "gender": _remote_gender(record),
            "nationality": str(_remote_value(record, "nationality", "country", default="")).strip()[:3],
            "email": str(_remote_value(record, "email", "rider_mail", default="")).strip(),
        }

        if rider is not None:
            diffs = _differences(rider, remote_values)
            if diffs:
                conflicts[str(rider.uci_id)] = diffs
                log.conflicts += 1
            log.matched += 1
            if not dry_run:
                rider.event_control_id = external_id or rider.event_control_id
                rider.event_control_synced = timezone.now()
                Rider.objects.filter(pk=rider.pk).update(
                    event_control_id=rider.event_control_id,
                    event_control_synced=rider.event_control_synced,
                )
            continue

        missing = [
            field for field in ("first_name", "last_name", "date_of_birth", "gender")
            if not remote_values.get(field)
        ]
        if uci_id is None or missing:
            skipped.append({"uci_id": str(uci_id or ""), "missing": missing or ["uci_id"]})
            log.skipped += 1
            continue

        log.created += 1
        created_riders.append(str(uci_id))
        if not dry_run:
            Rider.objects.create(
                uci_id=uci_id,
                first_name=remote_values["first_name"],
                last_name=remote_values["last_name"],
                date_of_birth=remote_values["date_of_birth"],
                gender=remote_values["gender"],
                nationality=remote_values["nationality"] or "CZE",
                email=remote_values["email"] or None,
                club=_resolve_rider_club(record),
                is_active=True,
                is_approved=False,
                event_control_id=external_id,
                event_control_synced=timezone.now(),
            )

    log.detail = {"conflicts": conflicts, "created": created_riders, "skipped": skipped[:20]}
    log.succeeded = True
    log.finished = timezone.now()
    log.save()
    audit_logger.info(
        "event_control_sync_riders source=%s received=%s matched=%s created=%s conflicts=%s skipped=%s dry_run=%s",
        source, log.received, log.matched, log.created, log.conflicts, log.skipped, dry_run,
    )
    return log


def last_successful_sync(entity):
    """Čas posledního úspěšného stažení dané entity (pro přírůstkový dotaz)."""
    log = (
        EventControlSyncLog.objects.filter(
            entity=entity,
            direction=EventControlSyncLog.Direction.PULL,
            succeeded=True,
            dry_run=False,
        )
        .order_by("-started")
        .first()
    )
    return log.started if log else None


def pull_from_event_control_admin(*, entities=("clubs", "riders"), since=None, source="cron", dry_run=False):
    """Stáhne a spáruje zvolené entity. Kluby se zpracují první (jezdci na ně navazují)."""
    client = EventControlAdminClient()
    if not client.configured:
        logger.info("Event Control Admin sync: EVENT_CONTROL_ADMIN_URL není nastavené, přeskočeno.")
        return []

    handlers = {"clubs": sync_clubs, "riders": sync_riders}
    logs = []
    for entity in entities:
        handler = handlers.get(entity)
        if handler is None:
            continue
        updated_since = since or last_successful_sync(entity)
        try:
            records = client.fetch(entity, updated_since=updated_since)
        except EventControlAdminUnavailable as error:
            logger.error("Event Control Admin sync (%s) selhala: %s", entity, error)
            logs.append(
                EventControlSyncLog.objects.create(
                    direction=EventControlSyncLog.Direction.PULL,
                    entity=entity,
                    source=source,
                    dry_run=dry_run,
                    succeeded=False,
                    finished=timezone.now(),
                    error=str(error),
                )
            )
            continue
        logs.append(handler(records, source=source, dry_run=dry_run))
    return logs
