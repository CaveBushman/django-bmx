from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.models import Account
from event.models_events import Event
from rider.models import Rider

from event.utils import normalize_uci_id


class Entry(models.Model):
    user = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, blank=True)
    transaction_id = models.CharField(max_length=255, default="", null=True, blank=True)
    rider = models.ForeignKey(Rider, db_constraint=False, on_delete=models.SET_NULL, null=True)
    is_beginner = models.BooleanField(default=False)
    is_20 = models.BooleanField(default=False)
    is_24 = models.BooleanField(default=False)
    class_beginner = models.CharField(max_length=255, default="", null=True, blank=True)
    class_20 = models.CharField(max_length=255, default="", null=True, blank=True)
    class_24 = models.CharField(max_length=255, default="", null=True, blank=True)
    fee_beginner = models.IntegerField(null=True, blank=True, default=0)
    fee_20 = models.IntegerField(null=True, blank=True, default=0)
    fee_24 = models.IntegerField(null=True, blank=True, default=0)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)
    payment_complete = models.BooleanField(default=False)
    checkout = models.BooleanField(default=False)
    date_of_payment = models.DateField(auto_now_add=True, null=True)
    customer_name = models.CharField(max_length=100, null=True, blank=True, default="")
    customer_email = models.CharField(max_length=100, null=True, blank=True, default="")
    created = models.DateField(auto_now_add=True, null=True)
    updated = models.DateField(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = "Registrace"
        verbose_name_plural = "Registrace"
        indexes = [
            models.Index(fields=["event", "payment_complete", "checkout"], name="event_entry_evt_pay_chk"),
            models.Index(fields=["user", "payment_complete"], name="event_entry_user_pay"),
            models.Index(fields=["transaction_date"], name="event_entry_tx_date"),
        ]

    def __str__(self):
        return f"{self.rider} - {self.event}"

    def total_fee_amount(self):
        return (self.fee_beginner or 0) + (self.fee_20 or 0) + (self.fee_24 or 0)

    def clean(self):
        super().clean()
        if self.checkout and not self.payment_complete:
            raise ValidationError({"checkout": _("Checkout lze zapnout jen u zaplacené registrace.")})
        if self.checkout and not self.user_id:
            raise ValidationError({"user": _("Checkout lze použít jen u registrace s přiřazeným uživatelem.")})
        if self.checkout and self.total_fee_amount() <= 0:
            raise ValidationError({"checkout": _("Checkout refund nelze vytvořit pro nulové nebo záporné startovné.")})


class EntryAuditLog(models.Model):
    class Action(models.TextChoices):
        CHECKOUT_CHANGED = "checkout_changed", "Změna checkout"
        REFUND_CONTEXT_CHANGED = "refund_context_changed", "Změna refund kontextu"

    entry = models.ForeignKey(Entry, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    actor = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="entry_audit_logs")
    action = models.CharField(max_length=40, choices=Action.choices)
    source = models.CharField(max_length=64, default="system")
    old_checkout = models.BooleanField(default=False)
    new_checkout = models.BooleanField(default=False)
    payment_complete = models.BooleanField(default=False)
    note = models.CharField(max_length=255, blank=True, default="")
    entry_id_snapshot = models.IntegerField(null=True, blank=True)
    entry_user_id_snapshot = models.IntegerField(null=True, blank=True)
    event_name_snapshot = models.CharField(max_length=255, blank=True, default="")
    rider_name_snapshot = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Audit registrace"
        verbose_name_plural = "Audit registrací"
        indexes = [
            models.Index(fields=["action", "created_at"], name="event_entryaudit_action_date"),
            models.Index(fields=["entry_id_snapshot", "created_at"], name="event_entryaudit_entry_date"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} #{self.entry_id_snapshot or self.entry_id or '-'}"


class EntryForeign(models.Model):
    transaction_id = models.CharField(max_length=255, default="")
    event = models.ForeignKey(Event, to_field="id", db_column="event", on_delete=models.SET_NULL, null=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    uci_id = models.CharField(max_length=20)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20)
    nationality = models.CharField(max_length=3)
    club = models.CharField(max_length=50)
    transponder = models.CharField(max_length=10)
    transponder_20 = models.CharField(max_length=10, null=True, blank=True, default="")
    transponder_24 = models.CharField(max_length=10, null=True, blank=True, default="")
    plate = models.CharField(max_length=20, null=True, blank=True, default="")
    is_20 = models.BooleanField(default=False)
    is_24 = models.BooleanField(default=False)
    is_elite = models.BooleanField(default=False)
    class_20 = models.CharField(max_length=255, default="", null=True, blank=True)
    class_24 = models.CharField(max_length=255, default="", null=True, blank=True)
    fee_20 = models.IntegerField(null=True, blank=True, default=0)
    fee_24 = models.IntegerField(null=True, blank=True, default=0)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)
    payment_complete = models.BooleanField(default=False)
    checkout = models.BooleanField(default=False)
    date_of_payment = models.DateField(auto_now_add=True, null=True)
    customer_name = models.CharField(max_length=100, null=True, blank=True, default="")
    customer_email = models.CharField(max_length=100, null=True, blank=True, default="")
    rider = models.ForeignKey(
        Rider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="foreign_entries",
        help_text="Propojení s českým jezdcem (pokud jezdec závodí pod zahraniční licencí)",
    )
    user = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="foreign_entries_created",
        help_text="Uživatel, který přihlášku vytvořil přes app (kreditní platba)",
    )

    def save(self, *args, **kwargs):
        self.uci_id = normalize_uci_id(self.uci_id)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Registrace zahraničních jezdců"
        verbose_name_plural = "Registrace zahraničních jezdců"
        indexes = [
            models.Index(fields=["event", "payment_complete", "checkout"], name="event_entryfor_evt_pay_chk"),
            models.Index(fields=["uci_id"], name="event_entryfor_uci"),
            models.Index(fields=["transaction_date"], name="event_entryfor_tx_date"),
        ]
