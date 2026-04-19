from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html, mark_safe

from .models import (
    Category,
    FlexiExportSettings,
    Order,
    OrderHistory,
    OrderItem,
    Product,
    ProductVariant,
    StockMovement,
    StockReservation,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "product_count")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")

    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = "Produktů"


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ("label", "price", "stock", "active", "sort_order")
    ordering = ("sort_order", "label")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "collection", "category", "price_range_display", "stock_display", "active", "updated")
    list_display_links = ("name",)
    list_editable = ("active",)
    list_filter = ("active", "category", "collection")
    search_fields = ("name", "subtitle", "collection", "description", "material", "fit_note")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created", "updated")
    inlines = [ProductVariantInline]
    fieldsets = (
        (None, {"fields": ("category", "collection", "name", "subtitle", "slug", "description", "image", "secondary_image", "variant_type", "active")}),
        ("Produktové informace", {"fields": ("material", "fit_note", "pickup_note")}),
        ("Metadata", {"fields": ("created", "updated"), "classes": ("collapse",)}),
    )

    def price_range_display(self, obj):
        return obj.price_range
    price_range_display.short_description = "Cena"

    def stock_display(self, obj):
        total = obj.total_stock
        if total == 0:
            return mark_safe('<span style="color:#dc2626;font-weight:700">Vyprodáno</span>')
        if total <= 5:
            return format_html('<span style="color:#d97706;font-weight:700">Málo ({} ks)</span>', total)
        return format_html('<span style="color:#16a34a;font-weight:700">{} ks</span>', total)
    stock_display.short_description = "Sklad"

    def save_formset(self, request, form, formset, change):
        before = {
            variant.pk: variant.stock
            for variant in formset.queryset
            if isinstance(variant, ProductVariant) and variant.pk
        }
        super().save_formset(request, form, formset, change)

        if formset.model is not ProductVariant:
            return

        for variant in form.instance.variants.all():
            old_stock = before.get(variant.pk)
            if old_stock is None:
                if variant.stock > 0:
                    StockMovement.record(
                        variant=variant,
                        movement_type=StockMovement.MovementType.RESTOCK,
                        quantity_delta=variant.stock,
                        stock_after=variant.stock,
                        actor=request.user,
                        note="Počáteční sklad při vytvoření varianty v adminu.",
                    )
                continue

            if old_stock != variant.stock:
                delta = variant.stock - old_stock
                movement_type = (
                    StockMovement.MovementType.RESTOCK
                    if delta > 0
                    else StockMovement.MovementType.MANUAL_ADJUSTMENT
                )
                StockMovement.record(
                    variant=variant,
                    movement_type=movement_type,
                    quantity_delta=delta,
                    stock_after=variant.stock,
                    actor=request.user,
                    note="Ruční úprava skladu v adminu.",
                )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("subtotal_display",)
    fields = ("variant", "quantity", "unit_price", "subtotal_display")

    def subtotal_display(self, obj):
        if obj.pk:
            return f"{obj.subtotal:,.0f} Kč".replace(",", "\u00a0")
        return "—"
    subtotal_display.short_description = "Mezisoučet"


@admin.action(description="Odečíst kredity a potvrdit objednávku")
def charge_credits_action(modeladmin, request, queryset):
    for order in queryset:
        try:
            order.charge_credits(actor=request.user)
            messages.success(
                request,
                f"Objednávka #{order.pk} potvrzena — odečteno {order.credits_charged} kreditů zákazníkovi {order.email}.",
            )
        except ValueError as e:
            messages.error(request, f"Objednávka #{order.pk}: {e}")


@admin.action(description="Označit jako odesláno")
def mark_shipped_action(modeladmin, request, queryset):
    updated = 0
    for order in queryset.exclude(status__in=[Order.Status.CANCELED, Order.Status.DELIVERED]):
        if order.status == Order.Status.SHIPPED:
            continue
        order.status = Order.Status.SHIPPED
        order.save(update_fields=["status", "updated"])
        OrderHistory.record(
            order=order,
            action=OrderHistory.Action.SHIPPED,
            actor=request.user,
            note="Objednávka označena jako odeslaná z Django adminu.",
        )
        updated += 1
    if updated:
        messages.success(request, f"Označeno jako odesláno: {updated} objednávek.")


@admin.action(description="Označit jako předáno")
def mark_delivered_action(modeladmin, request, queryset):
    updated = 0
    for order in queryset.exclude(status=Order.Status.CANCELED):
        if order.delivered_at:
            continue
        order.status = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
        order.delivered_by = request.user
        order.save(update_fields=["status", "delivered_at", "delivered_by", "updated"])
        OrderHistory.record(
            order=order,
            action=OrderHistory.Action.DELIVERED,
            actor=request.user,
            note="Objednávka označena jako předaná z Django adminu.",
        )
        updated += 1
    if updated:
        messages.success(request, f"Označeno jako předáno: {updated} objednávek.")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "invoice_number_display", "full_name", "email", "event", "status_badge", "paid_badge", "total_display", "delivered_at", "created")
    list_filter = ("status", "event", "created", "delivered_at")
    search_fields = ("first_name", "last_name", "email", "phone")
    readonly_fields = ("created", "updated", "total_display", "user", "credits_charged", "user_credit_display", "invoice_number", "credit_note_number", "delivered_at", "delivered_by")
    actions = [charge_credits_action, mark_shipped_action, mark_delivered_action]
    inlines = [OrderItemInline]
    fieldsets = (
        ("Stav a platba", {"fields": ("status", "user", "user_credit_display", "credits_charged", "invoice_number", "credit_note_number")}),
        ("Zákazník", {"fields": ("first_name", "last_name", "email", "phone")}),
        ("Doručení", {"fields": ("event", "delivered_at", "delivered_by")}),
        ("Poznámky", {"fields": ("note", "internal_note")}),
        ("Metadata", {"fields": ("created", "updated", "total_display"), "classes": ("collapse",)}),
    )

    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = "Zákazník"

    def invoice_number_display(self, obj):
        return obj.invoice_number or "—"
    invoice_number_display.short_description = "Číslo faktury"

    def status_badge(self, obj):
        colors = {
            "pending":   "#d97706",
            "confirmed": "#2563eb",
            "shipped":   "#7c3aed",
            "delivered": "#16a34a",
            "canceled":  "#dc2626",
        }
        color = colors.get(obj.status, "#64748b")
        return format_html(
            '<span style="color:{};font-weight:700">{}</span>',
            color,
            obj.get_status_display(),
        )
    status_badge.short_description = "Stav"

    def paid_badge(self, obj):
        if obj.is_paid:
            return format_html(
                '<span style="color:#16a34a;font-weight:700">✓ {} kr.</span>',
                obj.credits_charged,
            )
        return mark_safe('<span style="color:#94a3b8">Nezaplaceno</span>')
    paid_badge.short_description = "Platba"

    def total_display(self, obj):
        return f"{obj.total:,.0f} Kč".replace(",", "\u00a0")
    total_display.short_description = "Celkem"

    def user_credit_display(self, obj):
        if obj.user_id:
            credit = obj.user.credit
            color = "#16a34a" if credit >= int(obj.total or 0) else "#dc2626"
            return format_html(
                '<span style="color:{};font-weight:700">{} kreditů</span>',
                color,
                credit,
            )
        return "—"
    user_credit_display.short_description = "Kredity zákazníka"


@admin.action(description="Smazat vybrané expirované rezervace")
def delete_expired_reservations_action(modeladmin, request, queryset):
    deleted_count, _ = queryset.filter(expires_at__lte=timezone.now()).delete()
    if deleted_count:
        messages.success(request, f"Smazáno expirovaných rezervací: {deleted_count}.")
    else:
        messages.info(request, "Ve výběru nebyly žádné expirované rezervace.")


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = ("product_name", "variant_label", "session_key_short", "quantity", "expires_at", "active_badge")
    list_filter = ("expires_at", "variant__product")
    search_fields = ("session_key", "variant__label", "variant__product__name")
    readonly_fields = ("created", "updated")
    ordering = ("expires_at",)
    actions = [delete_expired_reservations_action]

    def product_name(self, obj):
        return obj.variant.product.name
    product_name.short_description = "Produkt"

    def variant_label(self, obj):
        return obj.variant.label
    variant_label.short_description = "Varianta"

    def session_key_short(self, obj):
        if not obj.session_key:
            return "—"
        return f"…{obj.session_key[-8:]}"
    session_key_short.short_description = "Session"

    def active_badge(self, obj):
        if obj.expires_at > timezone.now():
            return format_html('<span style="color:#16a34a;font-weight:700">Aktivní</span>')
        return format_html('<span style="color:#94a3b8;font-weight:700">Expirovaná</span>')
    active_badge.short_description = "Stav"


@admin.register(OrderHistory)
class OrderHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "action", "actor", "created", "note")
    list_filter = ("action", "created")
    search_fields = ("order__invoice_number", "order__email", "note", "actor__email", "actor__username")
    readonly_fields = ("order", "action", "actor", "note", "created")
    ordering = ("-created", "-id")

    def has_add_permission(self, request):
        return False


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created",
        "product_name",
        "variant_label",
        "movement_type",
        "quantity_delta_display",
        "stock_after",
        "order",
        "actor",
    )
    list_filter = ("movement_type", "created", "variant__product")
    search_fields = ("variant__product__name", "variant__label", "order__invoice_number", "note", "actor__email", "actor__username")
    readonly_fields = ("variant", "order", "movement_type", "quantity_delta", "stock_after", "actor", "note", "created")
    ordering = ("-created", "-id")

    def product_name(self, obj):
        return obj.variant.product.name
    product_name.short_description = "Produkt"

    def variant_label(self, obj):
        return obj.variant.label
    variant_label.short_description = "Varianta"

    def quantity_delta_display(self, obj):
        color = "#16a34a" if obj.quantity_delta > 0 else "#dc2626"
        sign = "+" if obj.quantity_delta > 0 else ""
        return format_html('<span style="color:{};font-weight:700">{}{}</span>', color, sign, obj.quantity_delta)
    quantity_delta_display.short_description = "Změna"

    def has_add_permission(self, request):
        return False


@admin.register(FlexiExportSettings)
class FlexiExportSettingsAdmin(admin.ModelAdmin):
    list_display = ("name", "invoice_document_type", "credit_note_document_type", "center_code", "updated")
    fieldsets = (
        ("Doklady", {"fields": ("name", "invoice_document_type", "credit_note_document_type", "payment_status_code")}),
        ("Položky a DPH", {"fields": ("price_type_code", "vat_rate_code", "vat_classification_code", "item_type_code", "unit_code")}),
        ("Organizace", {"fields": ("currency_code", "country_code", "center_code", "payment_method_code")}),
    )

    def has_add_permission(self, request):
        return not FlexiExportSettings.objects.exists()
