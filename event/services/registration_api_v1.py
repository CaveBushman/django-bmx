"""Obecný kontrakt Rider Registration API v1.

Kontrakt je popsaný v Event Control v ``docs/RIDER_REGISTRATION_API.md`` a je
záměrně **neutrální** — nemluví o BMX webu, ale o poskytovateli registrací.
Díky tomu si Event Control nemusí držet zvláštní dialekt pro každý systém, se
kterým se potká; každý poskytovatel doplní tyhle tři endpointy a hotovo.

Tři výdeje, dvě oprávnění:

* ``registrations_page`` — přihlášky jednoho závodu, údaji organizace,
* ``riders_page`` / ``clubs_page`` — celofederační master data, centrálními
  údaji (viz ``api.views.event_control``).

Doménová pravidla se tu **nekopírují**. Přihlášky staví
``event_control.build_entries_payload`` (startovní poplatky, zahraniční kluby,
přednost championship tabulky) a master data ``event_control_sync`` (co je
aktivní a schválené). Tento modul jen přesype výsledek do polí kontraktu.
Kdyby si vlastní verzi pravidel držel, rozešly by se — a rozdíl by se ukázal
až v startovní listině.
"""

from event.services.event_control import build_entries_payload
from event.services.event_control_sync import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    clubs_queryset,
    paginate,
    riders_queryset,
)

SCHEMA_VERSION = "1.0"

# Kontrakt chce ISO 3166-1 alpha-3. Web jinou zemi než Českou republiku
# u klubu needviduje, takže hodnota je konstanta, ne prázdné pole — Event
# Control z ní skládá stát klubu v centrálním registru.
CLUB_COUNTRY = "CZE"


def _envelope(payload: dict) -> dict:
    """Doplní ``schema_version`` — bez něj Event Control odpověď odmítne."""
    return {"schema_version": SCHEMA_VERSION, **payload}


# ---------------------------------------------------------------------------
# Část 1 — přihlášky jednoho závodu
# ---------------------------------------------------------------------------

def _gender(sex: str) -> str:
    """``m``/``f`` z interního exportu na ``M``/``F`` kontraktu."""
    return "F" if str(sex or "").strip().lower().startswith("f") else "M"


def _registration_id(rider: dict, start: dict) -> str:
    """Stabilní identifikátor jednoho startu.

    Kontrakt vyžaduje, aby se ``registration_id`` mezi opakovanými importy
    neměnilo. Klíčem je proto přihláška plus rozměr kola a příznak
    začátečníka — tedy přesně to, co jeden start odlišuje od druhého v téže
    přihlášce. Pořadové číslo v seznamu by se změnilo, jen kdyby někdo jiný
    odhlásil.
    """
    kind = "f" if rider.get("entry_type") == "foreign" else "d"
    suffix = "b" if start.get("is_beginner") else ""
    return f"{kind}-{rider.get('entry_id')}-{start.get('wheel')}{suffix}"


def _start_registration(rider: dict, start: dict) -> dict:
    """Jeden start jako jedna registrace kontraktu.

    Jedna registrace je jeden **start**, ne jeden jezdec: závodní software
    přiděluje jednu kategorii na start, takže jezdec přihlášený na 20" i 24"
    jsou dvě registrace se stejným ``uci_id``.
    """
    wheel_size = 24 if str(start.get("wheel")) == "24" else 20
    chip = start.get("transponder") or ""
    category_name = start.get("class") or ""
    # Championship tabulka má přednost před národní — pravidlo drží
    # `event_control._plate_for_start`, tady se jen vybírá číselná varianta,
    # protože startovní číslo v závodním software je celé číslo.
    bib = start.get("plate_champ") or start.get("plate_national")

    return {
        "registration_id": _registration_id(rider, start),
        "status": "confirmed" if rider.get("paid") else "pending",
        "rider": {
            "uci_id": rider.get("uci_id") or "",
            "first_name": rider.get("first_name") or "",
            "last_name": rider.get("last_name") or "",
            "birth_date": rider.get("date_of_birth"),
            "gender": _gender(rider.get("sex")),
            "elite": bool(rider.get("elite")),
            "nationality": rider.get("country") or "",
            "club": rider.get("club") or "",
            "bib": bib,
            "chip_id_20": chip if wheel_size == 20 else "",
            "chip_id_24": chip if wheel_size == 24 else "",
        },
        "category": {
            "code": category_name,
            "name": category_name,
            "wheel_size": wheel_size,
        },
    }


def registration_starts(event, include_unpaid: bool = False) -> list[dict]:
    """Všechny starty závodu jako plochý seznam registrací kontraktu."""
    payload = build_entries_payload(event, include_unpaid=include_unpaid)
    return [
        _start_registration(rider, start)
        for rider in payload["riders"]
        for start in rider["starts"]
    ]


def registrations_page(event, *, page=1, page_size=DEFAULT_PAGE_SIZE, include_unpaid=False) -> dict:
    """Stránka přihlášek podle obecného kontraktu.

    Stránkuje se v paměti nad hotovým seznamem startů, ne dotazem: závod má
    stovky přihlášek, ne miliony, a poskládat startovní listinu dvakrát je
    levnější než rozdělit pravidla o poplatcích a tabulkách mezi dvě cesty.
    """
    page_size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    page = max(1, int(page or 1))

    starts = registration_starts(event, include_unpaid=include_unpaid)
    offset = (page - 1) * page_size
    rows = starts[offset:offset + page_size]
    has_more = offset + len(rows) < len(starts)

    return _envelope({
        "event_code": str(event.event_code),
        "count": len(starts),
        "page": page,
        "page_size": page_size,
        "next_page": page + 1 if has_more else None,
        "registrations": rows,
    })


# ---------------------------------------------------------------------------
# Část 2 — centrální registr jezdců a klubů
# ---------------------------------------------------------------------------

def _club_record(club) -> dict:
    return {
        "external_id": str(club.id),
        "name": club.club_name or club.team_name or "",
        "team_name": club.team_name or "",
        "street": club.street or "",
        "city": club.city or "",
        "postal_code": club.zip_code or "",
        "country": CLUB_COUNTRY,
        "company_id": club.ico or "",
        "updated": club.updated.isoformat() if club.updated else None,
    }


def _rider_record(rider) -> dict:
    """Jezdec pro centrální registr.

    ``world_bib`` je championship tabulka pro 20". Registr drží jedno světové
    číslo, zatímco BMX Racing rozlišuje 20" a 24"; kontrakt proto výslovně
    říká, že poskytovatel se dvěma posílá to dvacetipalcové.
    """
    return {
        "external_id": str(rider.id),
        "uci_id": str(rider.uci_id or ""),
        "first_name": rider.first_name or "",
        "last_name": rider.last_name or "",
        "birth_date": rider.date_of_birth.isoformat() if rider.date_of_birth else None,
        "gender": "F" if rider.gender == "Žena" else "M",
        "nationality": rider.nationality or "",
        "club": rider.club.team_name if rider.club_id else "",
        "club_external_id": str(rider.club_id) if rider.club_id else "",
        "elite": rider.is_elite,
        "bib": rider.plate or None,
        "world_bib": rider.plate_champ_20 or None,
        "chip_id_20": rider.transponder_20 or "",
        "chip_id_24": rider.transponder_24 or "",
        "updated": rider.updated.isoformat() if rider.updated else None,
    }


def clubs_page(updated_since=None, limit=DEFAULT_PAGE_SIZE, offset=0, include_inactive=False) -> dict:
    return _envelope(
        paginate(clubs_queryset(updated_since, include_inactive), _club_record, limit, offset)
    )


def riders_page(updated_since=None, limit=DEFAULT_PAGE_SIZE, offset=0, include_inactive=False) -> dict:
    return _envelope(
        paginate(riders_queryset(updated_since, include_inactive), _rider_record, limit, offset)
    )
