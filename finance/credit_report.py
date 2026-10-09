"""Sestava zůstatků uživatelských kreditů k danému dni.

Zůstatky se počítají z účetní knihy (stejné složky jako
``event.credit._build_balance_components``), ne z denormalizovaného
``Account.credit``. Ten se v sestavě zobrazuje vedle pro kontrolu: rozdíl
k dnešku znamená, že uložený zůstatek nesedí s transakcemi.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time

from django.apps import apps
from django.db.models import Q, Sum
from django.utils import timezone

FILTER_NONZERO = "nonzero"
FILTER_POSITIVE = "positive"
FILTER_NEGATIVE = "negative"
FILTER_ALL = "all"
FILTER_CHOICES = [
    (FILTER_NONZERO, "Nenulové zůstatky"),
    (FILTER_POSITIVE, "Jen kladné"),
    (FILTER_NEGATIVE, "Jen záporné"),
    (FILTER_ALL, "Všichni uživatelé"),
]

SORT_NAME = "name"
SORT_BALANCE = "balance"
SORT_CHOICES = [
    (SORT_NAME, "Podle jména"),
    (SORT_BALANCE, "Podle zůstatku"),
]

# (app, model, filtr platnosti, znaménko) — kredit přičítá, ostatní odečítají.
_LEDGER = [
    ("event", "CreditTransaction", {"payment_complete": True}, 1),
    ("event", "DebetTransaction", {"payment_valid": True}, -1),
    ("rider", "RiderStatsCharge", {"payment_valid": True}, -1),
    ("rider", "TrainerClubCharge", {"payment_valid": True}, -1),
    ("rider", "MobileAppCharge", {"payment_valid": True}, -1),
]


@dataclass
class CreditBalanceRow:
    user_id: int
    name: str
    email: str
    is_active: bool
    credited: int
    spent: int
    balance: int
    stored_balance: int

    @property
    def mismatch(self):
        return self.stored_balance != self.balance


@dataclass
class CreditBalanceReport:
    as_of: object
    is_current: bool
    rows: list = field(default_factory=list)
    unassigned_balance: int = 0

    @property
    def total_balance(self):
        return sum(row.balance for row in self.rows)

    @property
    def total_positive(self):
        return sum(row.balance for row in self.rows if row.balance > 0)

    @property
    def total_negative(self):
        return sum(row.balance for row in self.rows if row.balance < 0)

    @property
    def mismatch_count(self):
        return sum(1 for row in self.rows if row.mismatch) if self.is_current else 0


def _ledger_sums(cutoff):
    """Vrátí {user_id: [připsáno, čerpáno]} a zůstatek transakcí bez uživatele."""
    sums = defaultdict(lambda: [0, 0])
    unassigned = 0
    # Staré záznamy bez data patří do každé sestavy (vznikly před zavedením data).
    date_filter = Q(transaction_date__lte=cutoff) | Q(transaction_date__isnull=True)
    for app_label, model_name, valid, sign in _LEDGER:
        model = apps.get_model(app_label, model_name)
        grouped = (
            model.objects.filter(date_filter, **valid)
            .values("user_id")
            .annotate(total=Sum("amount"))
        )
        for row in grouped:
            total = row["total"] or 0
            if row["user_id"] is None:
                unassigned += sign * total
                continue
            if sign > 0:
                sums[row["user_id"]][0] += total
            else:
                sums[row["user_id"]][1] += total
    return sums, unassigned


def build_credit_balance_report(*, as_of=None, balance_filter=FILTER_NONZERO, sort=SORT_NAME):
    today = timezone.localdate()
    as_of = min(as_of or today, today)
    cutoff = timezone.make_aware(datetime.combine(as_of, time.max))
    sums, unassigned = _ledger_sums(cutoff)

    Account = apps.get_model("accounts", "Account")
    accounts = Account.objects.only("id", "first_name", "last_name", "email", "username", "is_active", "credit")
    if balance_filter != FILTER_ALL:
        accounts = accounts.filter(pk__in=list(sums))

    rows = []
    for account in accounts:
        credited, spent = sums.get(account.pk, (0, 0))
        balance = credited - spent
        if balance_filter == FILTER_NONZERO and balance == 0:
            continue
        if balance_filter == FILTER_POSITIVE and balance <= 0:
            continue
        if balance_filter == FILTER_NEGATIVE and balance >= 0:
            continue
        name = f"{account.last_name} {account.first_name}".strip() or account.username or account.email
        rows.append(CreditBalanceRow(
            user_id=account.pk,
            name=name,
            email=account.email,
            is_active=account.is_active,
            credited=credited,
            spent=spent,
            balance=balance,
            stored_balance=account.credit,
        ))

    if sort == SORT_BALANCE:
        rows.sort(key=lambda row: (-row.balance, row.name.lower()))
    else:
        rows.sort(key=lambda row: (row.name.lower(), row.email.lower()))

    return CreditBalanceReport(
        as_of=as_of,
        is_current=as_of == today,
        rows=rows,
        unassigned_balance=unassigned,
    )
