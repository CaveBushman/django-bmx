from django.conf import settings
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone


class Category(models.Model):
    name = models.CharField("Název", max_length=100)
    slug = models.SlugField(unique=True)
    sort_order = models.PositiveSmallIntegerField("Pořadí", default=0)

    class Meta:
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorie"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    class VariantType(models.TextChoices):
        SIZE = "size", "Velikost"
        COLOR = "color", "Barva"
        OTHER = "other", "Jiné"

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="Kategorie",
    )
    name = models.CharField("Název", max_length=200)
    slug = models.SlugField(unique=True)
    subtitle = models.CharField("Krátký štítek", max_length=120, blank=True)
    collection = models.CharField("Kolekce", max_length=100, blank=True)
    description = models.TextField("Popis", blank=True)
    image = models.ImageField("Foto", upload_to="eshop/products/", blank=True)
    secondary_image = models.ImageField("Doplňková fotka", upload_to="eshop/products/", blank=True)
    material = models.CharField("Materiál", max_length=160, blank=True)
    fit_note = models.CharField("Poznámka ke střihu", max_length=160, blank=True)
    pickup_note = models.CharField("Poznámka k předání", max_length=200, blank=True)
    variant_type = models.CharField(
        "Typ varianty",
        max_length=10,
        choices=VariantType.choices,
        default=VariantType.SIZE,
    )
    active = models.BooleanField("Aktivní", default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produkt"
        verbose_name_plural = "Produkty"
        ordering = ["category__sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def price_range(self):
        prices = list(
            self.variants.filter(active=True).values_list("price", flat=True)
        )
        if not prices:
            return "—"
        lo, hi = min(prices), max(prices)
        if lo == hi:
            return f"{lo:,.0f} Kč".replace(",", "\u00a0")
        return f"{lo:,.0f}–{hi:,.0f} Kč".replace(",", "\u00a0")

    @property
    def total_stock(self):
        return sum(
            self.variants.filter(active=True).values_list("stock", flat=True)
        )


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name="Produkt",
    )
    label = models.CharField("Varianta", max_length=50)
    price = models.DecimalField("Cena (Kč)", max_digits=8, decimal_places=2)
    stock = models.PositiveIntegerField("Skladem (ks)", default=0)
    active = models.BooleanField("Aktivní", default=True)
    sort_order = models.PositiveSmallIntegerField("Pořadí", default=0)

    class Meta:
        verbose_name = "Varianta produktu"
        verbose_name_plural = "Varianty produktu"
        ordering = ["sort_order", "label"]

    def __str__(self):
        return f"{self.product.name} — {self.label}"


class StockReservation(models.Model):
    session_key = models.CharField("Session key", max_length=40, db_index=True)
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="stock_reservations",
        verbose_name="Varianta",
    )
    quantity = models.PositiveIntegerField("Počet kusů", default=1)
    expires_at = models.DateTimeField("Platí do")
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rezervace skladu"
        verbose_name_plural = "Rezervace skladu"
        unique_together = ("session_key", "variant")
        ordering = ["expires_at"]

    def __str__(self):
        return f"{self.variant} · {self.quantity} ks"

    @classmethod
    def cleanup_expired(cls, *, now=None):
        now = now or timezone.now()
        deleted_count, _ = cls.objects.filter(expires_at__lte=now).delete()
        return deleted_count


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Čeká na zpracování"
        CONFIRMED = "confirmed", "Potvrzena"
        SHIPPED = "shipped", "Odesláno"
        DELIVERED = "delivered", "Doručeno"
        CANCELED = "canceled", "Zrušena"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eshop_orders",
        verbose_name="Zákazník",
    )
    status = models.CharField(
        "Stav",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    first_name = models.CharField("Jméno", max_length=100)
    last_name = models.CharField("Příjmení", max_length=100)
    email = models.EmailField("E-mail")
    event = models.ForeignKey(
        "event.Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eshop_orders",
        verbose_name="Závod",
    )
    phone = models.CharField("Telefon", max_length=30, blank=True)
    street = models.CharField("Ulice a č.p.", max_length=200, blank=True)
    city = models.CharField("Město", max_length=100, blank=True)
    zip_code = models.CharField("PSČ", max_length=10, blank=True)
    note = models.TextField("Poznámka", blank=True)
    internal_note = models.TextField("Interní poznámka", blank=True)
    credits_charged = models.PositiveIntegerField("Odečtené kredity", null=True, blank=True)
    invoice_number = models.CharField("Číslo faktury", max_length=16, blank=True, unique=True)
    invoice_pdf = models.FileField("Faktura PDF", upload_to="eshop/invoices/", blank=True)
    credit_note_number = models.CharField("Číslo dobropisu", max_length=20, blank=True, unique=True)
    credit_note_pdf = models.FileField("Dobropis PDF", upload_to="eshop/credit-notes/", blank=True)
    delivered_at = models.DateTimeField("Předáno dne", null=True, blank=True)
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eshop_delivered_orders",
        verbose_name="Předal",
    )
    created = models.DateTimeField("Vytvořena", auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Objednávka"
        verbose_name_plural = "Objednávky"
        ordering = ["-created"]

    def __str__(self):
        return f"#{self.pk} — {self.first_name} {self.last_name}"

    @property
    def is_paid(self):
        return self.credits_charged is not None

    @property
    def is_cancelable(self):
        return (
            self.status not in {self.Status.CANCELED, self.Status.DELIVERED}
            and self.delivered_at is None
        )

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())

    def ensure_invoice_number(self, *, actor=None):
        if self.invoice_number:
            return self.invoice_number

        issue_date = timezone.localtime(self.created) if self.created else timezone.now()
        prefix = f"003{issue_date:%Y%m}"

        from django.db import transaction as db_tx

        with db_tx.atomic():
            locked = Order.objects.select_for_update().get(pk=self.pk)
            if locked.invoice_number:
                self.invoice_number = locked.invoice_number
                return locked.invoice_number

            last_number = (
                Order.objects.select_for_update()
                .filter(invoice_number__startswith=prefix)
                .order_by("-invoice_number")
                .values_list("invoice_number", flat=True)
                .first()
            )
            next_index = int(last_number[-3:]) + 1 if last_number else 1
            locked.invoice_number = f"{prefix}{next_index:03d}"
            locked.save(update_fields=["invoice_number"])
            self.invoice_number = locked.invoice_number
            OrderHistory.record(
                order=locked,
                action=OrderHistory.Action.INVOICE_ISSUED,
                actor=actor,
                note=f"Faktura {locked.invoice_number}",
            )
            return locked.invoice_number

    def ensure_credit_note_number(self, *, actor=None):
        if self.credit_note_number:
            return self.credit_note_number

        invoice_number = self.ensure_invoice_number(actor=actor)
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=self.pk)
            if locked.credit_note_number:
                self.credit_note_number = locked.credit_note_number
                return locked.credit_note_number
            locked.credit_note_number = f"{invoice_number}-D"
            locked.save(update_fields=["credit_note_number"])
            self.credit_note_number = locked.credit_note_number
            OrderHistory.record(
                order=locked,
                action=OrderHistory.Action.CREDIT_NOTE_ISSUED,
                actor=actor,
                note=f"Dobropis {locked.credit_note_number}",
            )
            return locked.credit_note_number

    def charge_credits(self, *, actor=None):
        from django.db import transaction as db_tx
        from event.models import CreditTransaction

        if not self.user_id:
            raise ValueError("Objednávka nemá přiřazeného zákazníka.")

        with db_tx.atomic():
            locked_order = Order.objects.select_for_update().get(pk=self.pk)
            if locked_order.is_paid:
                raise ValueError("Objednávka již byla zaplacena.")
            if not locked_order.user_id:
                raise ValueError("Objednávka nemá přiřazeného zákazníka.")

            user_model = locked_order.user.__class__
            user = user_model.objects.select_for_update().get(pk=locked_order.user_id)
            needed = int(locked_order.total)
            if user.credit < needed:
                raise ValueError(
                    f"Nedostatek kreditů — zákazník má {user.credit} Kč, objednávka stojí {needed} Kč."
                )

            items = list(locked_order.items.select_related("variant__product").all())
            variant_ids = [item.variant_id for item in items if item.variant_id]
            locked_variants = {
                variant.pk: variant
                for variant in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids)
            }

            for item in items:
                variant = locked_variants.get(item.variant_id)
                if variant is None or not variant.active:
                    raise ValueError("Některá z variant v objednávce už není dostupná.")
                if item.quantity > variant.stock:
                    raise ValueError(
                        f"Varianta {variant.product.name} / {variant.label} už nemá dostatek kusů skladem."
                    )

            for item in items:
                ProductVariant.objects.filter(pk=item.variant_id).update(stock=F("stock") - item.quantity)
                variant = locked_variants[item.variant_id]
                variant.refresh_from_db(fields=["stock"])
                StockMovement.record(
                    variant=variant,
                    order=locked_order,
                    movement_type=StockMovement.MovementType.ORDER_DECREMENT,
                    quantity_delta=-item.quantity,
                    stock_after=variant.stock,
                    actor=actor,
                    note=f"Objednávka #{locked_order.pk}",
                )

            locked_order.credits_charged = needed
            locked_order.status = Order.Status.CONFIRMED
            locked_order.save(update_fields=["credits_charged", "status", "updated"])
            CreditTransaction.objects.create(
                user=user,
                amount=-needed,
                kind=CreditTransaction.Kind.ESHOP_PURCHASE,
                payment_complete=True,
                transaction_id=f"eshop-order-{locked_order.pk}",
                payment_intent=f"Nákup v e-shopu č. {locked_order.pk}",
            )
            OrderHistory.record(
                order=locked_order,
                action=OrderHistory.Action.CREDIT_CHARGED,
                actor=actor,
                note=f"Odečteno {needed} kreditů.",
            )
            OrderHistory.record(
                order=locked_order,
                action=OrderHistory.Action.CONFIRMED,
                actor=actor,
                note="Objednávka potvrzena.",
            )
            self.credits_charged = locked_order.credits_charged
            self.status = locked_order.status

    def cancel_by_user(self, *, actor=None):
        from django.db import transaction as db_tx
        from event.models import CreditTransaction

        with db_tx.atomic():
            locked_order = Order.objects.select_for_update().get(pk=self.pk)
            if not locked_order.is_cancelable:
                raise ValueError("Tuto objednávku už nelze stornovat, protože byla předána nebo už je zrušená.")

            refund_amount = int(locked_order.credits_charged or 0)
            items = list(locked_order.items.select_related("variant").all())
            variant_ids = [item.variant_id for item in items if item.variant_id]
            locked_variants = {
                variant.pk: variant
                for variant in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids)
            }

            if refund_amount > 0:
                if not locked_order.user_id:
                    raise ValueError("Objednávka nemá navázaný uživatelský účet pro vrácení kreditu.")

                for item in items:
                    if item.variant_id in locked_variants:
                        ProductVariant.objects.filter(pk=item.variant_id).update(stock=F("stock") + item.quantity)
                        variant = locked_variants[item.variant_id]
                        variant.refresh_from_db(fields=["stock"])
                        StockMovement.record(
                            variant=variant,
                            order=locked_order,
                            movement_type=StockMovement.MovementType.CANCEL_RETURN,
                            quantity_delta=item.quantity,
                            stock_after=variant.stock,
                            actor=actor,
                            note=f"Storno objednávky #{locked_order.pk}",
                        )

                CreditTransaction.objects.create(
                    user=locked_order.user,
                    amount=refund_amount,
                    kind=CreditTransaction.Kind.ESHOP_REFUND,
                    payment_complete=True,
                    payment_intent=f"Storno objednávky č. {locked_order.pk}",
                    transaction_id=f"eshop-cancel-{locked_order.pk}",
                )
                OrderHistory.record(
                    order=locked_order,
                    action=OrderHistory.Action.CREDIT_REFUNDED,
                    actor=actor,
                    note=f"Vráceno {refund_amount} kreditů.",
                )

            locked_order.credits_charged = None
            locked_order.status = self.Status.CANCELED
            locked_order.save(update_fields=["credits_charged", "status", "updated"])
            OrderHistory.record(
                order=locked_order,
                action=OrderHistory.Action.CANCELED,
                actor=actor,
                note="Objednávka stornována.",
            )

            self.credits_charged = locked_order.credits_charged
            self.status = locked_order.status


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_items",
        verbose_name="Varianta",
    )
    quantity = models.PositiveSmallIntegerField("Počet", default=1)
    unit_price = models.DecimalField("Cena za kus (Kč)", max_digits=8, decimal_places=2)

    class Meta:
        verbose_name = "Položka objednávky"
        verbose_name_plural = "Položky objednávky"

    def __str__(self):
        return f"{self.variant} × {self.quantity}"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    @property
    def total(self):
        return self.subtotal


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        ORDER_DECREMENT = "order_decrement", "Odečet objednávkou"
        CANCEL_RETURN = "cancel_return", "Vrácení po stornu"
        MANUAL_ADJUSTMENT = "manual_adjustment", "Ruční úprava"
        RESTOCK = "restock", "Naskladnění"

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="stock_movements",
        verbose_name="Varianta",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
        verbose_name="Objednávka",
    )
    movement_type = models.CharField("Typ pohybu", max_length=32, choices=MovementType.choices)
    quantity_delta = models.IntegerField("Změna kusů")
    stock_after = models.PositiveIntegerField("Sklad po změně")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eshop_stock_movements",
        verbose_name="Provedl",
    )
    note = models.TextField("Poznámka", blank=True)
    created = models.DateTimeField("Vytvořeno", auto_now_add=True)

    class Meta:
        verbose_name = "Skladový pohyb"
        verbose_name_plural = "Skladové pohyby"
        ordering = ["-created", "-id"]

    def __str__(self):
        sign = "+" if self.quantity_delta > 0 else ""
        return f"{self.variant} · {sign}{self.quantity_delta} ks"

    @classmethod
    def record(
        cls,
        *,
        variant,
        movement_type,
        quantity_delta,
        stock_after,
        order=None,
        actor=None,
        note="",
    ):
        actor_obj = actor if getattr(actor, "is_authenticated", False) else None
        return cls.objects.create(
            variant=variant,
            order=order,
            movement_type=movement_type,
            quantity_delta=quantity_delta,
            stock_after=stock_after,
            actor=actor_obj,
            note=note or "",
        )


class StockAlertRequest(models.Model):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="stock_alert_requests",
        verbose_name="Varianta",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eshop_stock_alert_requests",
        verbose_name="Uživatel",
    )
    email = models.EmailField("E-mail")
    note = models.TextField("Poznámka", blank=True)
    fulfilled_at = models.DateTimeField("Vyřízeno dne", null=True, blank=True)
    created = models.DateTimeField("Vytvořeno", auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Požadavek na naskladnění"
        verbose_name_plural = "Požadavky na naskladnění"
        ordering = ["fulfilled_at", "-created"]

    def __str__(self):
        return f"{self.variant} · {self.email}"

    @property
    def is_open(self):
        return self.fulfilled_at is None


class OrderHistory(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Vytvořeno"
        CREDIT_CHARGED = "credit_charged", "Kredit odečten"
        CONFIRMED = "confirmed", "Potvrzeno"
        INVOICE_ISSUED = "invoice_issued", "Faktura vystavena"
        SHIPPED = "shipped", "Odesláno"
        DELIVERED = "delivered", "Předáno"
        CANCELED = "canceled", "Stornováno"
        CREDIT_REFUNDED = "credit_refunded", "Kredit vrácen"
        CREDIT_NOTE_ISSUED = "credit_note_issued", "Dobropis vystaven"
        NOTE = "note", "Poznámka"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history", verbose_name="Objednávka")
    action = models.CharField("Akce", max_length=32, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eshop_order_history_entries",
        verbose_name="Provedl",
    )
    note = models.TextField("Poznámka", blank=True)
    created = models.DateTimeField("Vytvořeno", auto_now_add=True)

    class Meta:
        verbose_name = "Historie objednávky"
        verbose_name_plural = "Historie objednávek"
        ordering = ["-created", "-id"]

    def __str__(self):
        return f"{self.order_id} · {self.get_action_display()}"

    @classmethod
    def record(cls, *, order, action, actor=None, note=""):
        actor_obj = actor if getattr(actor, "is_authenticated", False) else None
        return cls.objects.create(order=order, action=action, actor=actor_obj, note=note or "")


class FlexiExportSettings(models.Model):
    name = models.CharField("Název", max_length=80, default="Výchozí nastavení")
    invoice_document_type = models.CharField("Typ faktury", max_length=40, default="FAKTURA")
    credit_note_document_type = models.CharField("Typ dobropisu", max_length=40, default="DOBROPIS")
    price_type_code = models.CharField("Typ ceny", max_length=60, default="typCeny.bezDph")
    vat_rate_code = models.CharField("Sazba DPH", max_length=60, default="typSzbDph.dphOsv")
    item_type_code = models.CharField("Typ položky", max_length=60, default="typPolozky.obecny")
    payment_status_code = models.CharField("Stav úhrady", max_length=60, default="stavUhr.uhrazeno")
    currency_code = models.CharField("Měna", max_length=12, default="CZK")
    country_code = models.CharField("Stát", max_length=12, default="CZ")
    unit_code = models.CharField("Měrná jednotka", max_length=12, default="KS")
    center_code = models.CharField("Středisko", max_length=40, blank=True)
    payment_method_code = models.CharField("Forma úhrady", max_length=40, blank=True)
    vat_classification_code = models.CharField("Členění DPH", max_length=60, blank=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ABRA Flexi nastavení"
        verbose_name_plural = "ABRA Flexi nastavení"

    def __str__(self):
        return self.name

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"name": "Výchozí nastavení"})
        return obj
