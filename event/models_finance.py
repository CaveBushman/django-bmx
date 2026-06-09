import datetime
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from accounts.models import Account
from event.models_entries import Entry


class FinanceAuditLog(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Vytvoření"
        UPDATED = "updated", "Úprava"
        DELETED = "deleted", "Smazání"

    actor = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="finance_audit_logs")
    action = models.CharField(max_length=20, choices=Action.choices)
    source = models.CharField(max_length=64, default="admin")
    target_model = models.CharField(max_length=64)
    target_object_id = models.IntegerField(null=True, blank=True)
    target_user_id_snapshot = models.IntegerField(null=True, blank=True)
    amount_snapshot = models.IntegerField(default=0)
    transaction_kind_snapshot = models.CharField(max_length=64, blank=True, default="")
    payment_complete_snapshot = models.BooleanField(null=True, blank=True)
    payment_valid_snapshot = models.BooleanField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Audit financí"
        verbose_name_plural = "Audit financí"
        indexes = [
            models.Index(fields=["target_model", "created_at"], name="event_finaudit_model_date"),
            models.Index(fields=["target_object_id", "created_at"], name="event_finaudit_object_date"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.target_model} #{self.target_object_id or '-'}"


class DebetTransaction(models.Model):
    user = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    entry = models.ForeignKey(Entry, on_delete=models.SET_NULL, null=True, blank=True)
    foreign_entry = models.ForeignKey(
        "event.EntryForeign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="debet_transactions",
    )
    amount = models.IntegerField(default=0)
    payment_valid = models.BooleanField(default=True)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Debetní transakce"
        verbose_name_plural = "Debetní transakce"
        indexes = [
            models.Index(fields=["user", "transaction_date"], name="event_debet_user_date"),
            models.Index(fields=["entry"], name="event_debet_entry"),
        ]

    def __str__(self):
        user = self.user if self.user else "Neznámý uživatel"
        event = self.entry.event if self.entry else "Neznámý závod"
        rider = self.entry.rider if self.entry else "Neznámý jezdec"
        return f"{user} - {event} - {rider}"


class CreditTransaction(models.Model):
    class Kind(models.TextChoices):
        TOPUP = "topup", "Dobití kreditu"
        CHECKOUT_REFUND = "checkout_refund", "Vrácení startovného po checkoutu"
        ESHOP_PURCHASE = "eshop_purchase", "Nákup v e-shopu"
        ESHOP_REFUND = "eshop_refund", "Storno objednávky e-shopu"
        PROMO = "promo", "Promo kód"

    user = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    source_entry = models.ForeignKey(Entry, on_delete=models.CASCADE, null=True, blank=True, related_name="credit_transactions")
    amount = models.IntegerField(default=0)
    transaction_id = models.CharField(max_length=255, default="")
    payment_intent = models.CharField(max_length=255, default="")
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.TOPUP)
    payment_complete = models.BooleanField(default=False)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)
    uuid = models.UUIDField(default=uuid.uuid4, unique=False, editable=False)

    class Meta:
        verbose_name = "Kreditní transakce"
        verbose_name_plural = "Kreditní transakce"
        indexes = [
            models.Index(fields=["user", "payment_complete", "transaction_date"], name="event_credit_user_pay_date"),
            models.Index(fields=["transaction_id"], name="event_credit_tx_id"),
            models.Index(fields=["source_entry", "kind"], name="event_credit_entry_kind"),
            models.Index(fields=["kind", "payment_complete"], name="event_credit_kind_pay"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_entry", "kind"],
                condition=Q(source_entry__isnull=False, kind="checkout_refund"),
                name="event_credit_unique_checkout_refund_per_entry",
            ),
        ]

    def __str__(self):
        user = self.user if self.user else "Neznámý uživatel"
        return f"{user} - {self.amount} Kč"

    def clean(self):
        super().clean()
        if self.kind == self.Kind.CHECKOUT_REFUND and not self.source_entry_id:
            raise ValidationError({"source_entry": "Refund checkout transakce musí být navázaná na registraci."})


class StripeFee(models.Model):
    date = models.DateField(default=datetime.date.today)
    fee = models.DecimalField(default=0, decimal_places=2, max_digits=10)
    created = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Karetní poplatek"
        verbose_name_plural = "Karetní poplatky (STRIPE)"
        indexes = [
            models.Index(fields=["date"], name="event_stripefee_date"),
        ]
