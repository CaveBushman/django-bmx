"""Storno zaplacené přihlášky samotným uživatelem (web i mobilní API).

Pravidla se ověřují na serveru uvnitř transakce se zamčeným řádkem: přihláška
musí patřit uživateli, být zaplacená, bez checkoutu a lhůta pro odhlášení
(``can_unregister``) nesmí vypršet. Debetní transakce se nemažou — zneplatní
se (``payment_valid=False``), čímž se částka vrátí do kreditu a záznam
zůstane dohledatelný; změnu zapisuje ``FinanceAuditLog``.
"""

import logging

from django.db import transaction
from django.utils import timezone

from accounts.models import Account
from event.credit import calculate_user_balance
from event.models import DebetTransaction, Entry, FinanceAuditLog
from event.services.registration_status import can_unregister

audit_logger = logging.getLogger("audit")


class UnregistrationError(Exception):
    """Přihlášku nelze stornovat; zpráva je určená uživateli."""


def cancel_paid_entry(*, entry_id, user, source):
    """Stornuje přihlášku a vrátí debet do kreditu. Vrací vrácenou částku."""
    with transaction.atomic():
        entry = (
            Entry.objects.select_for_update()
            .select_related("event", "rider")
            .filter(pk=entry_id, user=user, payment_complete=True, checkout=False)
            .first()
        )
        if entry is None:
            raise UnregistrationError("Přihláška neexistuje nebo ji už nelze stornovat.")
        event = entry.event
        if event is None or (event.date and event.date < timezone.localdate()) or not can_unregister(event):
            raise UnregistrationError("Lhůta pro odhlášení již vypršela.")

        debets = list(
            DebetTransaction.objects.select_for_update().filter(entry=entry, user=user, payment_valid=True)
        )
        refunded = sum(debet.amount for debet in debets)
        note = f"Storno přihlášky #{entry.pk}: {event.name} – {entry.rider or 'neznámý jezdec'}"[:255]
        for debet in debets:
            debet.payment_valid = False
            debet.save(update_fields=["payment_valid"])
            FinanceAuditLog.objects.create(
                actor=user,
                action=FinanceAuditLog.Action.UPDATED,
                source=source,
                target_model="DebetTransaction",
                target_object_id=debet.pk,
                target_user_id_snapshot=debet.user_id,
                amount_snapshot=debet.amount,
                payment_valid_snapshot=False,
                note=note,
            )

        audit_logger.info(
            "confirmed_entry_deleted user_id=%s entry_id=%s event_id=%s refunded=%s source=%s",
            user.id, entry.pk, entry.event_id, refunded, source,
        )
        entry.delete()
        balance = calculate_user_balance(user.id)
        Account.objects.filter(pk=user.pk).update(credit=balance)
        user.credit = balance
    return refunded
