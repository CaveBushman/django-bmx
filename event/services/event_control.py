"""Podklady pro import přihlášených jezdců do BMX Event Control.

BMX Event Control se na server připojuje přes API: v nastavení organizace se
zadá server + username + password (viz ``Club.event_control_*``) a v nastavení
závodu kód závodu (``Event.event_code``). Tento modul staví JSON payload, který
odpovídá stejným datům jako REM export přihlášek (``event.entry.REMRiders``) —
jen strojově čitelně a bez mezikroku s XLSX souborem.

Jedna přihláška může obsahovat víc startů (začátečníci / 20" / 24"), proto má
každý jezdec seznam ``starts``; race software potřebuje jeden start = jedna třída.
"""

from django.utils import timezone

from club.models import Club
from event.func import (
    date_of_birth_resolve_rem_online,
    foreign_club_resolve,
    gender_resolve_small_letter,
    team_name_resolve,
)
from event.models import Entry, EntryForeign
from rider.models import ForeignRider

WHEEL_20 = "20"
WHEEL_24 = "24"


def _iso_date(value):
    return value.isoformat() if value else None


def _iso_datetime(value):
    return value.isoformat() if value else None


def _dob_display(value):
    """Datum narození ve tvaru DD.MM.YYYY (stejně jako v REM online exportu)."""
    return date_of_birth_resolve_rem_online(value) if value else ""


def _plate_for_start(plate_display, champ_plate):
    """Championship plate má přednost a přebírá prefix ``W`` jako v REM exportu."""
    if champ_plate:
        return f"W{champ_plate}"
    return plate_display or ""


def _plate_int(value):
    """Číselná hodnota tabulky, nebo ``None``.

    Tabulka se v exportu tiskne jako text (``plate_text`` unese i ``123A``
    a ``display_plate`` vrací pro prázdnou hodnotu pomlčku), ale závodní
    software potřebuje číslo. Cokoli, co není celé z číslic, čísly není —
    dosazovat za písmena nulu by z jezdce bez tabulky udělalo jezdce
    s tabulkou 0.
    """
    text = str(value or "").strip()
    return int(text) if text.isdigit() and int(text) > 0 else None


def event_payload(event) -> dict:
    """Metadata závodu pro spárování v BMX Event Control."""
    return {
        "code": str(event.event_code),
        "id": event.id,
        "name": event.name,
        "date": _iso_date(event.date),
        "type_for_ranking": event.type_for_ranking,
        "system": event.system or "",
        "double_race": event.double_race,
        "is_uci_race": event.is_uci_race,
        "uci_event_code": event.uci_event_code or "",
        "organizer": team_name_resolve(event.organizer),
        "organizer_id": event.organizer_id,
        "canceled": event.canceled,
        "registration_open": event.reg_open,
        "registration_open_from": _iso_datetime(event.reg_open_from),
        "registration_open_to": _iso_datetime(event.reg_open_to),
    }


def _domestic_rider_payload(entry) -> dict:
    rider = entry.rider
    national_plate = _plate_int(rider.plate_text) or _plate_int(rider.plate)
    starts = []

    if entry.is_beginner:
        starts.append({
            "wheel": WHEEL_20,
            "is_beginner": True,
            "class": entry.class_beginner or "",
            "plate": rider.plate_display or "",
            "plate_national": national_plate,
            "plate_champ": None,
            "transponder": rider.transponder_20 or "",
            "fee": entry.fee_beginner or 0,
        })
    if entry.is_20:
        starts.append({
            "wheel": WHEEL_20,
            "is_beginner": False,
            "class": entry.class_20 or "",
            "plate": _plate_for_start(rider.plate_display, rider.plate_champ_20),
            "plate_national": national_plate,
            "plate_champ": rider.plate_champ_20 or None,
            "transponder": rider.transponder_20 or "",
            "fee": entry.fee_20 or 0,
        })
    if entry.is_24:
        starts.append({
            "wheel": WHEEL_24,
            "is_beginner": False,
            "class": entry.class_24 or "",
            "plate": _plate_for_start(rider.plate_display, rider.plate_champ_24),
            "plate_national": national_plate,
            "plate_champ": rider.plate_champ_24 or None,
            "transponder": rider.transponder_24 or "",
            "fee": entry.fee_24 or 0,
        })

    return {
        "entry_id": entry.id,
        "entry_type": "domestic",
        "transaction_id": entry.transaction_id or "",
        "uci_id": str(rider.uci_id or ""),
        "first_name": rider.first_name or "",
        "last_name": rider.last_name or "",
        "email": rider.email or "",
        "club": team_name_resolve(rider.club),
        "team": "",
        "country": rider.nationality or "",
        "date_of_birth": _iso_date(rider.date_of_birth),
        "date_of_birth_display": _dob_display(rider.date_of_birth),
        "sex": gender_resolve_small_letter(rider.gender),
        "rider_type": "E" if rider.is_elite else "C",
        "elite": rider.is_elite,
        "licence_type": "U",
        "licence_valid": rider.valid_licence,
        "paid": entry.payment_complete,
        "fee_total": entry.total_fee_amount(),
        "updated": _iso_date(entry.updated),
        "starts": starts,
    }


def _foreign_rider_payload(entry, foreign_clubs) -> dict:
    # Zahraniční přihláška nese jedinou tabulku a žádnou championship —
    # tu přiděluje národní federace, ne pořadatel jednoho závodu.
    national_plate = _plate_int(entry.plate)
    starts = []

    if entry.is_20:
        starts.append({
            "wheel": WHEEL_20,
            "is_beginner": False,
            "class": entry.class_20 or "",
            "plate": entry.plate or "",
            "plate_national": national_plate,
            "plate_champ": None,
            "transponder": entry.transponder_20 or entry.transponder or "",
            "fee": entry.fee_20 or 0,
        })
    if entry.is_24:
        starts.append({
            "wheel": WHEEL_24,
            "is_beginner": False,
            "class": entry.class_24 or "",
            "plate": entry.plate or "",
            "plate_national": national_plate,
            "plate_champ": None,
            "transponder": entry.transponder_24 or entry.transponder or "",
            "fee": entry.fee_24 or 0,
        })

    club = foreign_clubs.get(str(entry.uci_id)) or entry.club or foreign_club_resolve(entry.nationality or "")

    return {
        "entry_id": entry.id,
        "entry_type": "foreign",
        "transaction_id": entry.transaction_id or "",
        "uci_id": str(entry.uci_id or ""),
        "first_name": entry.first_name or "",
        "last_name": entry.last_name or "",
        "email": entry.customer_email or "",
        "club": club,
        "team": "",
        "country": entry.nationality or "",
        "date_of_birth": _iso_date(entry.date_of_birth),
        "date_of_birth_display": _dob_display(entry.date_of_birth),
        "sex": gender_resolve_small_letter(entry.gender),
        "rider_type": "E" if entry.is_elite else "C",
        "elite": entry.is_elite,
        "licence_type": "U",
        "licence_valid": True,
        "paid": entry.payment_complete,
        "fee_total": (entry.fee_20 or 0) + (entry.fee_24 or 0),
        "updated": _iso_datetime(entry.transaction_date),
        "starts": starts,
    }


def build_entries_payload(event, include_unpaid: bool = False) -> dict:
    """Vrátí přihlášené jezdce závodu ve formátu pro BMX Event Control.

    Výchozí filtr je stejný jako u REM exportu: zaplacené a neodhlášené
    přihlášky. ``include_unpaid=True`` přidá i nezaplacené (rozpracované) —
    hodí se jen pro kontrolu, ne pro startovní listinu.
    """
    entry_filter = {"event": event.id, "checkout": False}
    if not include_unpaid:
        entry_filter["payment_complete"] = True

    domestic = (
        Entry.objects.filter(**entry_filter)
        .exclude(rider__isnull=True)
        .select_related("rider", "rider__club")
        .order_by("rider__last_name", "rider__first_name")
    )
    foreign = EntryForeign.objects.filter(**entry_filter).order_by("last_name", "first_name")

    foreign_clubs = {
        str(uci_id): club
        for uci_id, club in ForeignRider.objects.filter(
            uci_id__in=list(foreign.values_list("uci_id", flat=True)),
            club__gt="",
        ).values_list("uci_id", "club")
    }

    riders = [_domestic_rider_payload(entry) for entry in domestic]
    riders += [_foreign_rider_payload(entry, foreign_clubs) for entry in foreign]

    return {
        "event": event_payload(event),
        "generated_at": timezone.now().isoformat(),
        "include_unpaid": include_unpaid,
        "count": len(riders),
        "starts_count": sum(len(rider["starts"]) for rider in riders),
        "riders": riders,
    }


def authenticate_club(username: str, password: str):
    """Ověří přístupové údaje organizace. Vrací ``Club`` nebo ``None``."""
    if not username or not password:
        return None
    club = Club.objects.filter(event_control_username=username, event_control_enabled=True).first()
    if club is None or not club.check_event_control_password(password):
        return None
    return club


def club_can_access_event(club, event) -> bool:
    """Organizace smí stahovat přihlášky jen ke svým závodům."""
    return club is not None and event.organizer_id == club.id


def touch_club_access(club) -> None:
    Club.objects.filter(pk=club.pk).update(event_control_last_access=timezone.now())
