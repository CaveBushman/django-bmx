import logging

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from event.models import CreditTransaction, Entry, Event, Result
from rider.models import Rider


logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Event)
def delete_old_event_files(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = Event.objects.get(pk=instance.pk)
    except Event.DoesNotExist:
        return

    files_to_delete = []

    def _schedule_delete_if_changed(old_field, new_field):
        old_name = getattr(old_field, "name", "") or ""
        new_name = getattr(new_field, "name", "") or ""
        if old_name and old_name != new_name:
            files_to_delete.append((old_field.storage, old_name))

    _schedule_delete_if_changed(old.xls_results, instance.xls_results)
    _schedule_delete_if_changed(old.bem_backup, instance.bem_backup)
    _schedule_delete_if_changed(old.bem_backup_2, instance.bem_backup_2)
    _schedule_delete_if_changed(old.full_results, instance.full_results)
    _schedule_delete_if_changed(old.fast_riders, instance.fast_riders)
    _schedule_delete_if_changed(old.series, instance.series)
    _schedule_delete_if_changed(old.proposition, instance.proposition)

    if not files_to_delete:
        return

    def _delete_replaced_files():
        for storage, file_name in files_to_delete:
            try:
                storage.delete(file_name)
            except Exception:
                logger.exception("Nepodařilo se smazat původní soubor eventu: %s", file_name)

    transaction.on_commit(_delete_replaced_files)


@receiver(pre_save, sender=Event)
def commission_fee(sender, instance, **kwargs):
    if instance.commission_fee == 0:
        if instance.type_for_ranking in {"Český pohár", "Česká liga", "Moravská liga"}:
            instance.commission_fee = 20
        else:
            instance.commission_fee = 5


@receiver(post_save, sender=Result)
def sync_rider_categories_from_result(sender, instance, **kwargs):
    if not instance.rider_id or instance.is_beginner:
        return

    if instance.is_20:
        Rider.objects.filter(uci_id=instance.rider_id, is_20=False).update(is_20=True)
    else:
        Rider.objects.filter(uci_id=instance.rider_id, is_24=False).update(is_24=True)


@receiver(pre_save, sender=Entry)
def remember_entry_checkout_state(sender, instance, **kwargs):
    from event.services.checkout_refunds import capture_entry_state

    capture_entry_state(instance)


@receiver(pre_save, sender=Entry)
def validate_entry_business_rules(sender, instance, **kwargs):
    instance.clean()


@receiver(post_save, sender=Entry)
@receiver(post_delete, sender=Entry)
def invalidate_cache_on_entry_change(sender, instance, **kwargs):
    cache.delete("active_riders")


@receiver(post_save, sender=Entry)
def sync_checkout_refund_credit(sender, instance, created, **kwargs):
    from event.services.checkout_refunds import (
        log_checkout_related_changes,
        log_checkout_transition,
        sync_checkout_refund_credit as sync_checkout_refund_credit_service,
    )

    sync_checkout_refund_credit_service(instance)
    log_checkout_transition(instance, created=created)
    if not created:
        log_checkout_related_changes(instance)


@receiver(post_delete, sender=Entry)
def delete_checkout_refund_credit_on_entry_delete(sender, instance, **kwargs):
    from event.services.checkout_refunds import delete_checkout_refund_credit

    delete_checkout_refund_credit(instance)


@receiver(post_save, sender=CreditTransaction)
def update_user_balance(sender, instance, **kwargs):
    if instance.user:
        from event.credit import calculate_user_balance

        new_balance = calculate_user_balance(instance.user.id)
        instance.user.credit = new_balance
        instance.user.save()


@receiver(post_delete, sender=CreditTransaction)
def update_user_balance_after_delete(sender, instance, **kwargs):
    if instance.user:
        from event.credit import calculate_user_balance

        new_balance = calculate_user_balance(instance.user.id)
        instance.user.credit = new_balance
        instance.user.save()
