import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils.translation import gettext as _


logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


def capture_entry_state(entry):
    if not entry.pk:
        entry._previous_state = {
            "checkout": False,
            "user_id": None,
            "event_id": None,
            "payment_complete": False,
            "fee_beginner": 0,
            "fee_20": 0,
            "fee_24": 0,
        }
        return

    from event.models import Entry

    previous = Entry.objects.filter(pk=entry.pk).values(
        "checkout",
        "user_id",
        "event_id",
        "payment_complete",
        "fee_beginner",
        "fee_20",
        "fee_24",
    ).first()
    entry._previous_state = previous or {
        "checkout": False,
        "user_id": None,
        "event_id": None,
        "payment_complete": False,
        "fee_beginner": 0,
        "fee_20": 0,
        "fee_24": 0,
    }


def get_audit_context(entry):
    return getattr(entry, "_audit_context", {}) or {}


def get_checkout_refund_amount(entry):
    return (
        (entry.fee_beginner or 0)
        + (entry.fee_20 or 0)
        + (entry.fee_24 or 0)
    )


def get_checkout_refund_amount_from_state(state):
    state = state or {}
    return (
        (state.get("fee_beginner") or 0)
        + (state.get("fee_20") or 0)
        + (state.get("fee_24") or 0)
    )


def get_checkout_refund_transaction_id(entry):
    return f"checkout-refund-entry-{entry.pk}"


def get_checkout_refund_payment_intent(entry):
    event_name = entry.event.name if entry.event else _("Neznámý závod")
    return _("Vrácení startovného za závod %(event_name)s") % {
        "event_name": event_name,
    }


def get_checkout_refund_credit(entry):
    from event.models import CreditTransaction
    from django.db.models import Q

    return (
        CreditTransaction.objects.filter(
            Q(source_entry=entry)
            | Q(
                kind=CreditTransaction.Kind.CHECKOUT_REFUND,
                transaction_id=get_checkout_refund_transaction_id(entry),
            )
        )
        .order_by("id")
        .first()
    )


def delete_checkout_refund_credit(entry):
    refund = get_checkout_refund_credit(entry)
    if refund is not None:
        notify_checkout_refund_removed(entry, refund)
        refund.delete()
        logger.info("entry_checkout_refund_deleted entry_id=%s credit_id=%s", entry.pk, refund.pk)


def _get_checkout_notification_recipients(entry, *, include_admins=False):
    recipients = []
    if entry.user and entry.user.email:
        recipients.append(entry.user.email)
    if include_admins:
        from accounts.models import Account

        admin_emails = list(
            Account.objects.filter(is_admin=True)
            .exclude(email="")
            .values_list("email", flat=True)
        )
        recipients.extend(admin_emails)

    unique_recipients = []
    for recipient in recipients:
        if recipient and recipient not in unique_recipients:
            unique_recipients.append(recipient)
    return unique_recipients


def _send_checkout_refund_notification(*, subject, message, recipients):
    if not recipients:
        return

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "checkout_refund_notification_failed recipients=%s subject=%s",
            ",".join(recipients),
            subject,
        )


def notify_checkout_refund_created(entry, refund):
    recipients = _get_checkout_notification_recipients(entry, include_admins=True)
    event_name = entry.event.name if entry.event else _("Neznámý závod")
    subject = _("Checkout refund vytvořen: %(event_name)s") % {
        "event_name": event_name,
    }
    message = _(
        "Byla vytvořena vratka startovného za závod %(event_name)s.\n\n"
        "Jezdec: %(rider)s\n"
        "Uživatel: %(user)s\n"
        "Částka: %(amount)s Kč\n"
        "Registrace ID: %(entry_id)s\n"
        "Transakce: %(payment_intent)s\n"
    ) % {
        "event_name": event_name,
        "rider": entry.rider,
        "user": entry.user,
        "amount": refund.amount,
        "entry_id": entry.pk,
        "payment_intent": refund.payment_intent,
    }
    _send_checkout_refund_notification(
        subject=subject,
        message=message,
        recipients=recipients,
    )


def notify_checkout_refund_removed(entry, refund):
    recipients = _get_checkout_notification_recipients(entry, include_admins=True)
    event_name = entry.event.name if entry.event else _("Neznámý závod")
    subject = _("Checkout refund zrušen: %(event_name)s") % {
        "event_name": event_name,
    }
    message = _(
        "Vratka startovného za závod %(event_name)s byla zrušena.\n\n"
        "Jezdec: %(rider)s\n"
        "Uživatel: %(user)s\n"
        "Částka: %(amount)s Kč\n"
        "Registrace ID: %(entry_id)s\n"
        "Transakce: %(payment_intent)s\n"
    ) % {
        "event_name": event_name,
        "rider": entry.rider,
        "user": entry.user,
        "amount": refund.amount,
        "entry_id": entry.pk,
        "payment_intent": refund.payment_intent,
    }
    _send_checkout_refund_notification(
        subject=subject,
        message=message,
        recipients=recipients,
    )


def sync_checkout_refund_credit(entry):
    from event.models import CreditTransaction

    if not entry.pk:
        return None

    with transaction.atomic():
        amount = get_checkout_refund_amount(entry)
        should_have_refund = bool(
            entry.checkout and entry.payment_complete and entry.user_id and amount > 0
        )
        refund = get_checkout_refund_credit(entry)

        if not should_have_refund:
            if refund is not None:
                notify_checkout_refund_removed(entry, refund)
                refund.delete()
                logger.info(
                    "entry_checkout_refund_removed entry_id=%s credit_id=%s reason=state_mismatch",
                    entry.pk,
                    refund.pk,
                )
            return None

        refund_defaults = {
            "user": entry.user,
            "amount": amount,
            "transaction_id": get_checkout_refund_transaction_id(entry),
            "payment_intent": get_checkout_refund_payment_intent(entry),
            "payment_complete": True,
            "kind": CreditTransaction.Kind.CHECKOUT_REFUND,
            "source_entry": entry,
        }

        if refund is None:
            refund = CreditTransaction.objects.create(**refund_defaults)
            notify_checkout_refund_created(entry, refund)
            logger.info(
                "entry_checkout_refund_created entry_id=%s credit_id=%s amount=%s",
                entry.pk,
                refund.pk,
                amount,
            )
            return refund

        if refund.user_id != entry.user_id:
            old_refund_id = refund.pk
            notify_checkout_refund_removed(entry, refund)
            refund.delete()
            refund = CreditTransaction.objects.create(**refund_defaults)
            notify_checkout_refund_created(entry, refund)
            logger.info(
                "entry_checkout_refund_recreated entry_id=%s old_credit_id=%s new_credit_id=%s reason=user_changed",
                entry.pk,
                old_refund_id,
                refund.pk,
            )
            return refund

        changed_fields = []
        for field_name, value in (
            ("amount", amount),
            ("transaction_id", refund_defaults["transaction_id"]),
            ("payment_intent", refund_defaults["payment_intent"]),
            ("payment_complete", True),
            ("kind", CreditTransaction.Kind.CHECKOUT_REFUND),
            ("source_entry", entry),
        ):
            if getattr(refund, field_name) != value:
                setattr(refund, field_name, value)
                changed_fields.append(field_name)

        if changed_fields:
            refund.save(update_fields=changed_fields)
            logger.info(
                "entry_checkout_refund_updated entry_id=%s credit_id=%s fields=%s",
                entry.pk,
                refund.pk,
                ",".join(changed_fields),
            )

        return refund


def create_entry_audit_log(
    entry,
    *,
    action,
    old_checkout,
    new_checkout,
    actor=None,
    source="system",
    note="",
):
    from event.models import EntryAuditLog

    return EntryAuditLog.objects.create(
        entry=entry,
        actor=actor,
        action=action,
        source=source,
        old_checkout=old_checkout,
        new_checkout=new_checkout,
        payment_complete=bool(entry.payment_complete),
        note=note or "",
        entry_id_snapshot=entry.pk,
        event_name_snapshot=entry.event.name if entry.event else "",
        rider_name_snapshot=str(entry.rider) if entry.rider else "",
        entry_user_id_snapshot=entry.user_id,
    )


def log_checkout_transition(entry, *, created=False):
    from event.models import EntryAuditLog

    previous = getattr(entry, "_previous_state", {}) or {}
    previous_checkout = bool(previous.get("checkout", False))
    current_checkout = bool(entry.checkout)
    audit_context = get_audit_context(entry)

    if created and not current_checkout:
        return

    if not created and previous_checkout == current_checkout:
        return

    create_entry_audit_log(
        entry,
        action=EntryAuditLog.Action.CHECKOUT_CHANGED,
        old_checkout=previous_checkout,
        new_checkout=current_checkout,
        actor=audit_context.get("actor"),
        source=audit_context.get("source", "model_signal"),
        note=audit_context.get("note", ""),
    )

    audit_logger.info(
        "entry_checkout_changed entry_id=%s user_id=%s event_id=%s old_checkout=%s new_checkout=%s payment_complete=%s source=%s actor_user_id=%s",
        entry.pk,
        entry.user_id,
        entry.event_id,
        previous_checkout,
        current_checkout,
        entry.payment_complete,
        audit_context.get("source", "model_signal"),
        getattr(audit_context.get("actor"), "id", None),
    )


def log_checkout_related_changes(entry):
    from event.models import EntryAuditLog

    previous = getattr(entry, "_previous_state", {}) or {}
    audit_context = get_audit_context(entry)
    had_or_has_checkout = bool(previous.get("checkout")) or bool(entry.checkout)

    if not had_or_has_checkout:
        return

    previous_amount = get_checkout_refund_amount_from_state(previous)
    current_amount = get_checkout_refund_amount(entry)
    if previous_amount != current_amount:
        create_entry_audit_log(
            entry,
            action=EntryAuditLog.Action.REFUND_CONTEXT_CHANGED,
            old_checkout=bool(previous.get("checkout")),
            new_checkout=bool(entry.checkout),
            actor=audit_context.get("actor"),
            source=audit_context.get("source", "model_signal"),
            note=_("Změna částky refundu: %(old_amount)s -> %(new_amount)s Kč") % {
                "old_amount": previous_amount,
                "new_amount": current_amount,
            },
        )

    if previous.get("user_id") != entry.user_id:
        create_entry_audit_log(
            entry,
            action=EntryAuditLog.Action.REFUND_CONTEXT_CHANGED,
            old_checkout=bool(previous.get("checkout")),
            new_checkout=bool(entry.checkout),
            actor=audit_context.get("actor"),
            source=audit_context.get("source", "model_signal"),
            note=_("Změna uživatele refundu: %(old_user_id)s -> %(new_user_id)s") % {
                "old_user_id": previous.get("user_id"),
                "new_user_id": entry.user_id,
            },
        )

    if previous.get("event_id") != entry.event_id:
        create_entry_audit_log(
            entry,
            action=EntryAuditLog.Action.REFUND_CONTEXT_CHANGED,
            old_checkout=bool(previous.get("checkout")),
            new_checkout=bool(entry.checkout),
            actor=audit_context.get("actor"),
            source=audit_context.get("source", "model_signal"),
            note=_("Změna závodu refundu: %(old_event_id)s -> %(new_event_id)s") % {
                "old_event_id": previous.get("event_id"),
                "new_event_id": entry.event_id,
            },
        )


def apply_entry_checkout(entry, *, checkout, actor=None, source="service", note=""):
    if bool(entry.checkout) == bool(checkout):
        return False

    with transaction.atomic():
        entry._audit_context = {
            "actor": actor,
            "source": source,
            "note": note,
        }
        entry.checkout = bool(checkout)
        entry.save(update_fields=["checkout"])
    return True
