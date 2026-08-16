"""Zápis zpět od Event Control — trvalá změna čipu u rampy.

Jediná část kontraktu Rider Registration API v1, která data **mění**
(``docs/RIDER_REGISTRATION_API.md``, část 3). Ostatní endpointy jen vydávají,
co web ví.

Proč to vůbec existuje: čip jezdce vede web, Event Control si ho stahuje do
svého registru a při konfliktu vyhrává stažená hodnota. Když ale obsluha
u rampy vymění jezdci čip a odpoví, že jde o změnu **trvalou**, je to oprava
údaje, který web drží — a bez zápisu zpět by ji nejbližší synchronizace
přepsala zpátky na starou. Jezdec by pak příští závod začal zase se špatným
čipem, i když ho u rampy někdo poctivě opravil.

Změna se zapisuje do stejné historie (``RiderTransponderChange``), jakou plní
admin webu. Kdyby si tenhle modul vedl vlastní evidenci, byly by dvě historie
téhož jezdce a ani jedna by nebyla úplná.

Zapisuje se **jen** čip. Jméno, klub ani tabulku Event Control nemění — ty
spravuje federace tady a přepisovat je z rampy by znamenalo, že překlep
v jednom závodě přepíše, co web ví o celé sezóně.
"""

import logging

from django.db import transaction

from event.utils import normalize_uci_id
from rider.models import Rider, RiderTransponderChange

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")

SCHEMA_VERSION = "1.0"

# Kontrakt pojmenovává kola ``chip_id_20`` / ``chip_id_24``; web je má jako
# ``transponder_20`` / ``transponder_24``. Překlad je tady, ne v pohledu —
# aby druhý konzument nemusel hádat, které pole je které.
CHIP_FIELDS = {
    "chip_id_20": ("transponder_20", RiderTransponderChange.SLOT_20),
    "chip_id_24": ("transponder_24", RiderTransponderChange.SLOT_24),
}

# Delší kód se do sloupce nevejde (``max_length=8``). Uříznout ho by znamenalo
# uložit čip, na který jezdec nikdy neodjede — a nikdo by se to nedozvěděl.
MAX_CHIP_LENGTH = Rider._meta.get_field("transponder_20").max_length


class ChipWritebackError(Exception):
    """Odmítnutí, které má smysl vrátit volajícímu. ``status`` je HTTP kód."""

    def __init__(self, message, *, status=422):
        super().__init__(message)
        self.message = message
        self.status = status


def _requested_chips(payload):
    """Dvojice (pole kontraktu, hodnota), které volající skutečně poslal.

    Chybějící klíč znamená „neposláno“ a hodnota zůstane. Prázdný řetězec je
    naopak platná změna: „jezdec už čip nemá“ je zjištění obsluhy, ne
    nevyplněné pole. Tím se tenhle endpoint liší od zbytku kontraktu, kde
    prázdná hodnota nikdy nepřepisuje.
    """
    requested = []
    for key in CHIP_FIELDS:
        if key not in payload:
            continue
        value = payload[key]
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ChipWritebackError(f"Pole {key} musí být řetězec.")
        value = value.strip().upper()
        if len(value) > MAX_CHIP_LENGTH:
            raise ChipWritebackError(
                f"Kód čipu smí mít nejvýš {MAX_CHIP_LENGTH} znaků, přišlo {len(value)}."
            )
        requested.append((key, value))
    if not requested:
        raise ChipWritebackError("Očekává se chip_id_20 nebo chip_id_24.")
    return requested


def _conflicting_rider(rider, field, chip):
    """Jiný aktivní jezdec, který už tenhle čip má.

    Dva jezdci na jednom kódu znamenají, že časomíra jednomu z nich přiřadí
    cizí průjezdy. Radši odmítnout a nechat to na federaci, než tiše přepsat
    čip někomu, kdo o tom neví.
    """
    if not chip:
        return None
    return (
        Rider.objects.filter(is_active=True, **{field: chip})
        .exclude(pk=rider.pk)
        .first()
    )


@transaction.atomic
def apply_chip_change(payload, *, changed_by=None):
    """Zapíše čip z požadavku Event Control. Vrací (jezdec, seznam změn).

    Idempotentní: stejný čip poslaný podruhé projde a nic nezmění. Kontrakt to
    vyžaduje, protože Event Control odesílá z fronty a pokus se může zopakovat
    po výpadku spojení, o kterém protistrana neví.
    """
    raw_uci_id = payload.get("uci_id")
    uci_id = normalize_uci_id(raw_uci_id)
    if not uci_id:
        # Nesmysl v cestě je „takového jezdce tu nemáme", ne vadné tělo —
        # kontrakt na 404 nezkouší znovu, kdežto na 422 by volající hádal,
        # co má v těle opravit.
        if raw_uci_id:
            raise ChipWritebackError(f"Jezdec s UCI ID {raw_uci_id} tu není.", status=404)
        raise ChipWritebackError("Chybí uci_id.")

    requested = _requested_chips(payload)

    # `select_for_update` proto, že dva závody mohou odbavovat téhož jezdce
    # současně — bez zámku by si poslední zápis přepsal historii toho prvního.
    rider = Rider.objects.select_for_update().filter(uci_id=int(uci_id)).first()
    if rider is None:
        raise ChipWritebackError(f"Jezdec s UCI ID {uci_id} tu není.", status=404)

    changes = []
    for key, chip in requested:
        field, slot = CHIP_FIELDS[key]
        previous = getattr(rider, field) or ""
        if previous == chip:
            continue
        conflict = _conflicting_rider(rider, field, chip)
        if conflict is not None:
            raise ChipWritebackError(
                f"Čip {chip} už má přiřazený jezdec {conflict}.", status=409
            )
        setattr(rider, field, chip or None)
        changes.append((field, slot, previous, chip))

    if not changes:
        return rider, []

    rider.save(update_fields=[field for field, _slot, _old, _new in changes])
    RiderTransponderChange.objects.bulk_create(
        [
            RiderTransponderChange(
                rider=rider,
                slot=slot,
                old_transponder=old or "",
                new_transponder=new or "",
                # Obvykle prázdné: obsluha u rampy je jméno v Event Control,
                # ne účet na webu. Kdo to byl, zůstává v audit logu níž.
                changed_by=changed_by,
            )
            for _field, slot, old, new in changes
        ]
    )
    audit_logger.info(
        "event_control_chip_writeback uci_id=%s changes=%s source=%s actor=%s",
        uci_id,
        ",".join(f"{slot}:{old or '-'}->{new or '-'}" for _f, slot, old, new in changes),
        payload.get("source") or "-",
        payload.get("changed_by") or "-",
    )
    return rider, changes


def response_payload(rider, changes):
    """Odpověď kontraktu — co teď o jezdci platí."""
    return {
        "schema_version": SCHEMA_VERSION,
        "uci_id": str(rider.uci_id),
        "chip_id_20": rider.transponder_20 or "",
        "chip_id_24": rider.transponder_24 or "",
        "changed": [slot for _field, slot, _old, _new in changes],
    }
