import csv
import hashlib
import logging
import uuid
from decimal import Decimal
from xml.etree import ElementTree as ET

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import transaction as db_tx
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from bmx.rate_limit import get_rate_limit_subject, is_rate_limited
from .cart import Cart
from .forms import CheckoutForm, StockAlertRequestForm
from .invoice import generate_credit_note, generate_invoice
from .models import (
    FlexiExportSettings,
    Order,
    OrderHistory,
    OrderItem,
    Product,
    ProductVariant,
    StockAlertRequest,
    StockReservation,
)


RESERVATION_MINUTES = 10
logger = logging.getLogger(__name__)


def _csv_safe(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    text = value
    if text and text[0] in {"=", "+", "-", "@", "\t", "\r"}:
        return f"'{text}"
    return text


def _checkout_token(request):
    token = request.session.get("eshop_checkout_token")
    if not token:
        token = uuid.uuid4().hex
        request.session["eshop_checkout_token"] = token
        request.session.modified = True
    return token


def _checkout_submit_lock_key(request, token, cart_obj):
    session_key = _ensure_session_key(request)
    cart_signature = ",".join(f"{key}:{value}" for key, value in sorted(cart_obj.raw().items()))
    digest = hashlib.sha256(cart_signature.encode("utf-8")).hexdigest()[:16]
    return f"eshop-checkout-submit:{session_key}:{token}:{digest}"


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@staff_member_required
def index(request):
    cleaned_reservation_count = StockReservation.cleanup_expired()
    products = Product.objects.select_related("category").prefetch_related("variants")
    orders = Order.objects.select_related("user", "event", "delivered_by").prefetch_related("items__variant__product")
    today = timezone.localdate()
    now = timezone.now()
    pickup_orders = orders.filter(
        event__isnull=False,
        event__eshop_pickup_enabled=True,
        delivered_at__isnull=True,
        status__in=[Order.Status.CONFIRMED, Order.Status.SHIPPED],
    ).order_by("event__date", "created")
    delivered_today = orders.filter(
        event__eshop_pickup_enabled=True,
        delivered_at__date=today,
        status=Order.Status.DELIVERED,
    ).order_by("-delivered_at")
    pickup_events = (
        orders.filter(event__isnull=False, event__eshop_pickup_enabled=True)
        .values_list("event__id", "event__name", "event__date")
        .distinct()
    )
    selected_pickup_event = request.GET.get("pickup_event")
    if selected_pickup_event:
        pickup_orders = pickup_orders.filter(event_id=selected_pickup_event)
        delivered_today = delivered_today.filter(event_id=selected_pickup_event)

    pickup_item_count = (
        pickup_orders.aggregate(total_quantity=Sum("items__quantity")).get("total_quantity") or 0
    )
    active_reservations = (
        StockReservation.objects.select_related("variant__product")
        .filter(expires_at__gt=now)
        .order_by("expires_at", "variant__product__name", "variant__label")
    )
    reservation_variant_rows = (
        active_reservations.values("variant__product__name", "variant__label")
        .annotate(total_reserved=Sum("quantity"))
        .order_by("-total_reserved", "variant__product__name", "variant__label")[:6]
    )
    open_stock_alerts = (
        StockAlertRequest.objects.select_related("variant__product", "user")
        .filter(fulfilled_at__isnull=True)
        .order_by("-created")
    )
    stock_alert_variant_rows = (
        open_stock_alerts.values("variant__product__name", "variant__label", "variant__stock")
        .annotate(request_count=Count("id"))
        .order_by("-request_count", "variant__product__name", "variant__label")[:6]
    )

    context = {
        "products": products,
        "product_count": products.count(),
        "order_count": orders.count(),
        "pending_count": orders.filter(status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.SHIPPED]).count(),
        "recent_orders": orders.order_by("-created")[:10],
        "pickup_orders": pickup_orders[:12],
        "pickup_count": pickup_orders.count(),
        "pickup_item_count": pickup_item_count,
        "pickup_events": pickup_events,
        "selected_pickup_event": selected_pickup_event or "",
        "delivered_today": delivered_today[:10],
        "delivered_today_count": delivered_today.count(),
        "today": today,
        "low_stock_variants": _low_stock_variants(),
        "active_reservations": active_reservations[:6],
        "reservation_count": active_reservations.count(),
        "reserved_piece_count": active_reservations.aggregate(total_quantity=Sum("quantity")).get("total_quantity") or 0,
        "reservation_variant_rows": reservation_variant_rows,
        "cleaned_reservation_count": cleaned_reservation_count,
        "open_stock_alerts": open_stock_alerts[:8],
        "open_stock_alert_count": open_stock_alerts.count(),
        "stock_alert_variant_rows": stock_alert_variant_rows,
    }
    return render(request, "eshop/index.html", context)


def _pickup_orders_queryset():
    return (
        Order.objects.select_related("event", "user")
        .prefetch_related("items__variant__product")
        .filter(
            event__isnull=False,
            event__eshop_pickup_enabled=True,
            delivered_at__isnull=True,
            status__in=[Order.Status.CONFIRMED, Order.Status.SHIPPED],
        )
        .order_by("event__date", "event__name", "created")
    )


@staff_member_required
def export_pickup_orders_csv(request):
    orders = _pickup_orders_queryset()
    event_id = request.GET.get("event")
    if event_id:
        orders = orders.filter(event_id=event_id)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response.write("\ufeff")
    response["Content-Disposition"] = 'attachment; filename="eshop-vydej.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Cislo faktury",
            "Zakaznik",
            "E-mail",
            "Telefon",
            "Zavod",
            "Datum zavodu",
            "Stav",
            "Polozky",
            "Celkem (Kc)",
            "Poznamka zakaznika",
        ]
    )
    for order in orders:
        items_text = ", ".join(
            f"{item.variant.product.name if item.variant else 'Produkt'} / "
            f"{item.variant.label if item.variant else '-'} x {item.quantity}"
            for item in order.items.all()
        )
        writer.writerow(
            [_csv_safe(value) for value in [
                order.invoice_number or order.pk,
                f"{order.first_name} {order.last_name}".strip(),
                order.email,
                order.phone,
                order.event.name if order.event else "",
                order.event.date.strftime("%d.%m.%Y") if order.event and order.event.date else "",
                order.get_status_display(),
                items_text,
                int(order.total),
                order.note,
            ]]
        )
    return response


@staff_member_required
def export_accounting_orders_csv(request):
    orders = (
        Order.objects.select_related("event", "user")
        .prefetch_related("items__variant__product")
        .filter(invoice_number__gt="")
        .order_by("-created")
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response.write("\ufeff")
    response["Content-Disposition"] = 'attachment; filename="eshop-ucetni-export.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Typ dokladu",
            "Cislo dokladu",
            "Datum vytvoreni",
            "Zakaznik",
            "E-mail",
            "Zavod",
            "Stav objednavky",
            "Polozky",
            "Castka dokladu (Kc)",
            "Odecet kreditu (Kc)",
            "Vratka kreditu (Kc)",
        ]
    )
    for order in orders:
        items_text = ", ".join(
            f"{item.variant.product.name if item.variant else 'Produkt'} / "
            f"{item.variant.label if item.variant else '-'} x {item.quantity}"
            for item in order.items.all()
        )
        charged = int(order.total) if order.status != Order.Status.CANCELED else 0
        refunded = int(order.total) if order.credit_note_number else 0
        writer.writerow(
            [_csv_safe(value) for value in [
                "Faktura",
                order.invoice_number,
                timezone.localtime(order.created).strftime("%d.%m.%Y %H:%M"),
                f"{order.first_name} {order.last_name}".strip(),
                order.email,
                order.event.name if order.event else "",
                order.get_status_display(),
                items_text,
                int(order.total),
                charged,
                0,
            ]]
        )
        if order.credit_note_number:
            writer.writerow(
                [_csv_safe(value) for value in [
                    "Dobropis",
                    order.credit_note_number,
                    timezone.localtime(order.updated).strftime("%d.%m.%Y %H:%M"),
                    f"{order.first_name} {order.last_name}".strip(),
                    order.email,
                    order.event.name if order.event else "",
                    order.get_status_display(),
                    items_text,
                    -int(order.total),
                    0,
                    refunded,
                ]]
            )
    return response


@staff_member_required
def export_flexi_xml(request):
    orders = (
        Order.objects.select_related("event", "user")
        .prefetch_related("items__variant__product")
        .filter(invoice_number__gt="")
        .order_by("created", "pk")
    )

    settings = FlexiExportSettings.get_solo()
    root = ET.Element("winstrom", version="1.0")
    for order in orders:
        _append_flexi_invoice(root, order, settings)
        if order.credit_note_number:
            _append_flexi_credit_note(root, order, settings)

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    response = HttpResponse(xml_bytes, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="eshop-flexi.xml"'
    return response


@staff_member_required
def pickup_print_list(request):
    event_id = request.GET.get("event")
    orders = _pickup_orders_queryset()
    selected_event = None
    if event_id:
        orders = orders.filter(event_id=event_id)
        if orders.exists():
            selected_event = orders.first().event

    total_pieces = orders.aggregate(total_quantity=Sum("items__quantity")).get("total_quantity") or 0
    return render(
        request,
        "eshop/pickup-print.html",
        {
            "orders": orders,
            "selected_event": selected_event,
            "event_id": event_id or "",
            "total_orders": orders.count(),
            "total_pieces": total_pieces,
            "generated_at": timezone.now(),
        },
    )


def _append_xml_text(parent, tag, value):
    if value is None or value == "":
        return None
    element = ET.SubElement(parent, tag)
    element.text = str(value)
    return element


def _customer_display_name(order):
    full_name = f"{order.first_name} {order.last_name}".strip()
    return full_name or order.email


def _flexi_code(value):
    return f"code:{value}" if value and not str(value).startswith("code:") else value


def _append_flexi_common_fields(node, order, settings):
    customer_name = _customer_display_name(order)
    _append_xml_text(node, "typDokl", _flexi_code(settings.invoice_document_type))
    _append_xml_text(node, "kod", order.invoice_number)
    _append_xml_text(node, "varSym", order.invoice_number)
    _append_xml_text(node, "datVyst", timezone.localdate(order.created).isoformat())
    _append_xml_text(node, "duzpPuv", timezone.localdate(order.created).isoformat())
    _append_xml_text(node, "datSplat", timezone.localdate(order.created).isoformat())
    _append_xml_text(node, "stavUhrK", settings.payment_status_code)
    _append_xml_text(node, "mena", _flexi_code(settings.currency_code))
    _append_xml_text(node, "stredisko", _flexi_code(settings.center_code) if settings.center_code else "")
    _append_xml_text(node, "formaUhradyCis", _flexi_code(settings.payment_method_code) if settings.payment_method_code else "")
    _append_xml_text(node, "nazFirmy", customer_name)
    _append_xml_text(node, "kontaktJmeno", customer_name)
    _append_xml_text(node, "kontaktEmail", order.email)
    _append_xml_text(node, "kontaktTel", order.phone)
    _append_xml_text(node, "ulice", order.street)
    _append_xml_text(node, "mesto", order.city)
    _append_xml_text(node, "psc", order.zip_code)
    _append_xml_text(node, "stat", _flexi_code(settings.country_code))
    popis = f"E-shop objednávka {order.invoice_number}"
    if order.event:
        popis = f"{popis} · {order.event.name}"
    _append_xml_text(node, "popis", popis)
    _append_xml_text(node, "sumCelkem", f"{Decimal(order.total):.2f}")


def _append_flexi_invoice(root, order, settings):
    invoice = ET.SubElement(root, "faktura-vydana")
    _append_xml_text(invoice, "id", f"ext:ESHOP:{order.invoice_number}")
    _append_flexi_common_fields(invoice, order, settings)

    items_el = ET.SubElement(invoice, "polozkyFaktury")
    for item in order.items.all():
        row = ET.SubElement(items_el, "faktura-vydana-polozka")
        product_name = item.variant.product.name if item.variant and item.variant.product else "Produkt"
        variant_label = item.variant.label if item.variant else ""
        row_name = product_name
        if variant_label:
            row_name = f"{row_name} ({variant_label})"
        _append_xml_text(row, "nazev", row_name)
        _append_xml_text(row, "typPolozkyK", settings.item_type_code)
        _append_xml_text(row, "typCenyDphK", settings.price_type_code)
        _append_xml_text(row, "typSzbDphK", settings.vat_rate_code)
        _append_xml_text(row, "clenDph", settings.vat_classification_code)
        _append_xml_text(row, "mnozMj", item.quantity)
        _append_xml_text(row, "mj", _flexi_code(settings.unit_code))
        _append_xml_text(row, "cenaMj", f"{Decimal(item.unit_price):.2f}")
        _append_xml_text(row, "sumZkl", f"{Decimal(item.subtotal):.2f}")
        _append_xml_text(row, "sumCelkem", f"{Decimal(item.subtotal):.2f}")


def _append_flexi_credit_note(root, order, settings):
    credit_note = ET.SubElement(root, "faktura-vydana")
    _append_xml_text(credit_note, "id", f"ext:ESHOP:{order.credit_note_number}")
    _append_xml_text(credit_note, "typDokl", _flexi_code(settings.credit_note_document_type))
    _append_xml_text(credit_note, "kod", order.credit_note_number)
    _append_xml_text(credit_note, "varSym", order.credit_note_number)
    _append_xml_text(credit_note, "datVyst", timezone.localdate(order.updated).isoformat())
    _append_xml_text(credit_note, "duzpPuv", timezone.localdate(order.updated).isoformat())
    _append_xml_text(credit_note, "datSplat", timezone.localdate(order.updated).isoformat())
    _append_xml_text(credit_note, "mena", _flexi_code(settings.currency_code))
    _append_xml_text(credit_note, "stredisko", _flexi_code(settings.center_code) if settings.center_code else "")
    _append_xml_text(credit_note, "formaUhradyCis", _flexi_code(settings.payment_method_code) if settings.payment_method_code else "")
    _append_xml_text(credit_note, "nazFirmy", _customer_display_name(order))
    _append_xml_text(credit_note, "kontaktJmeno", _customer_display_name(order))
    _append_xml_text(credit_note, "kontaktEmail", order.email)
    _append_xml_text(credit_note, "kontaktTel", order.phone)
    _append_xml_text(credit_note, "stat", _flexi_code(settings.country_code))
    _append_xml_text(credit_note, "popis", f"Dobropis k faktuře {order.invoice_number}")
    _append_xml_text(credit_note, "sumCelkem", f"{Decimal(order.total) * Decimal('-1'):.2f}")

    relation = ET.SubElement(credit_note, "vytvor-vazbu-dobropis")
    _append_xml_text(relation, "dobropisovanyDokl", f"code:{order.invoice_number}")

    items_el = ET.SubElement(credit_note, "polozkyFaktury")
    for item in order.items.all():
        row = ET.SubElement(items_el, "faktura-vydana-polozka")
        product_name = item.variant.product.name if item.variant and item.variant.product else "Produkt"
        variant_label = item.variant.label if item.variant else ""
        row_name = product_name
        if variant_label:
            row_name = f"{row_name} ({variant_label})"
        _append_xml_text(row, "nazev", row_name)
        _append_xml_text(row, "typPolozkyK", settings.item_type_code)
        _append_xml_text(row, "typCenyDphK", settings.price_type_code)
        _append_xml_text(row, "typSzbDphK", settings.vat_rate_code)
        _append_xml_text(row, "clenDph", settings.vat_classification_code)
        _append_xml_text(row, "mnozMj", f"-{item.quantity}")
        _append_xml_text(row, "mj", _flexi_code(settings.unit_code))
        _append_xml_text(row, "cenaMj", f"{Decimal(item.unit_price):.2f}")
        _append_xml_text(row, "sumZkl", f"{Decimal(item.subtotal) * Decimal('-1'):.2f}")
        _append_xml_text(row, "sumCelkem", f"{Decimal(item.subtotal) * Decimal('-1'):.2f}")


@require_POST
@staff_member_required
def mark_pickup_order_shipped(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("event"),
        pk=order_id,
        event__isnull=False,
    )
    if order.status == Order.Status.CANCELED:
        messages.error(request, "Zrušenou objednávku nelze označit jako odeslanou.")
    elif order.delivered_at or order.status == Order.Status.DELIVERED:
        messages.info(request, "Objednávka už byla předaná, stav odesláno už nedává smysl.")
    elif order.status == Order.Status.SHIPPED:
        messages.info(request, "Objednávka už je označena jako odeslaná.")
    else:
        order.status = Order.Status.SHIPPED
        order.save(update_fields=["status", "updated"])
        OrderHistory.record(
            order=order,
            action=OrderHistory.Action.SHIPPED,
            actor=request.user,
            note="Objednávka označena jako odeslaná.",
        )
        messages.success(
            request,
            f"Objednávka {order.invoice_number or order.pk} byla označena jako odeslaná.",
        )

    redirect_url = reverse("eshop:index")
    pickup_event = request.POST.get("pickup_event")
    if pickup_event:
        redirect_url = f"{redirect_url}?pickup_event={pickup_event}"
    return redirect(redirect_url)


@require_POST
@staff_member_required
def mark_pickup_order_delivered(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("event"),
        pk=order_id,
        event__isnull=False,
    )
    if order.status == Order.Status.CANCELED:
        messages.error(request, "Zrušenou objednávku nelze označit jako předanou.")
    elif order.delivered_at:
        messages.info(request, "Objednávka už byla jako předaná označena.")
    else:
        order.status = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
        order.delivered_by = request.user
        order.save(update_fields=["status", "delivered_at", "delivered_by", "updated"])
        OrderHistory.record(
            order=order,
            action=OrderHistory.Action.DELIVERED,
            actor=request.user,
            note="Objednávka označena jako předaná z výdejového panelu.",
        )
        messages.success(
            request,
            f"Objednávka {order.invoice_number or order.pk} byla označena jako předaná.",
        )

    redirect_url = reverse("eshop:index")
    pickup_event = request.POST.get("pickup_event")
    if pickup_event:
        redirect_url = f"{redirect_url}?pickup_event={pickup_event}"
    return redirect(redirect_url)


def shop(request):
    StockReservation.cleanup_expired()
    cart_obj = Cart(request)
    category_slug = request.GET.get("kategorie")
    query = (request.GET.get("q") or "").strip()
    products_qs = (
        Product.objects
        .select_related("category")
        .prefetch_related("variants")
        .filter(active=True)
        .order_by("category__sort_order", "name")
    )
    if category_slug:
        products_qs = products_qs.filter(category__slug=category_slug)
    if query:
        products_qs = products_qs.filter(
            Q(name__icontains=query)
            | Q(subtitle__icontains=query)
            | Q(collection__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        )

    reserved_all = _reserved_quantities_by_variant()

    products = list(products_qs)
    for p in products:
        active_variants = [v for v in p.variants.all() if v.active]
        for v in active_variants:
            v.available_stock = max(v.stock - reserved_all.get(v.pk, 0), 0)
        p.active_variants = active_variants
        p.available_stock = sum(v.available_stock for v in active_variants)

    featured_product = products[0] if products else None

    from .models import Category
    categories = Category.objects.filter(products__active=True).distinct().order_by("sort_order", "name")

    product_count = Product.objects.filter(active=True).count()
    variant_count = ProductVariant.objects.filter(active=True, product__active=True).count()

    context = {
        "products": products,
        "featured_product": featured_product,
        "categories": categories,
        "active_category": category_slug,
        "query": query,
        "product_count": product_count,
        "category_count": categories.count(),
        "variant_count": variant_count,
        "cart_count": len(cart_obj),
        "has_cart_items": bool(cart_obj),
    }
    return render(request, "eshop/shop.html", context)


def product_detail(request, slug):
    StockReservation.cleanup_expired()
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related("variants"),
        slug=slug,
        active=True,
    )
    session_key = request.session.session_key
    reserved_by_others = _reserved_quantities_by_variant(exclude_session_key=session_key)
    cart_obj = Cart(request)
    variants = list(product.variants.filter(active=True))
    for v in variants:
        v.available_stock = max(v.stock - reserved_by_others.get(v.pk, 0), 0)
        v.cart_quantity = cart_obj.get_quantity(v.pk)
        v.addable_stock = max(v.available_stock - v.cart_quantity, 0)
    total_available_stock = sum(v.available_stock for v in variants)
    stock_alert_form = StockAlertRequestForm(product=product, user=request.user)
    context = {
        "product": product,
        "variants": variants,
        "total_available_stock": total_available_stock,
        "stock_alert_form": stock_alert_form,
        "has_sold_out_variants": any(v.available_stock == 0 for v in variants),
    }
    return render(request, "eshop/product_detail.html", context)


@require_POST
def request_stock_alert(request, slug):
    product = get_object_or_404(
        Product.objects.prefetch_related("variants"),
        slug=slug,
        active=True,
    )
    limited, _attempts = is_rate_limited(
        "eshop-stock-alert",
        get_rate_limit_subject(request, scope_to_user=True),
        window_seconds=60 * 15,
        max_attempts=8,
    )
    if limited:
        messages.error(request, "Požadavků je příliš mnoho. Zkus to prosím znovu za několik minut.")
        return redirect("eshop:product-detail", slug=product.slug)

    form = StockAlertRequestForm(request.POST, product=product, user=request.user)
    if not form.is_valid():
        messages.error(request, "Požadavek na hlídání dostupnosti se nepodařilo uložit. Zkontroluj e-mail a variantu.")
        return redirect("eshop:product-detail", slug=product.slug)

    variant = form.cleaned_data["variant"]
    if variant.product_id != product.pk or variant.stock > 0:
        messages.error(request, "Vybraná varianta už není vyprodaná nebo nepatří k produktu.")
        return redirect("eshop:product-detail", slug=product.slug)

    email = form.cleaned_data["email"].strip().lower()
    existing = StockAlertRequest.objects.filter(
        variant=variant,
        email__iexact=email,
        fulfilled_at__isnull=True,
    ).first()
    if existing:
        messages.info(request, "Tento požadavek už evidujeme. Jakmile budeme naskladňovat, uvidíme ho v poptávce.")
        return redirect("eshop:product-detail", slug=product.slug)

    StockAlertRequest.objects.create(
        variant=variant,
        user=request.user if request.user.is_authenticated else None,
        email=email,
        note=form.cleaned_data.get("note", ""),
    )
    messages.success(request, "Požadavek na naskladnění je uložený. Pomůže nám rozhodnout, co doplnit na sklad.")
    return redirect("eshop:product-detail", slug=product.slug)


@staff_member_required
def admin_order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("user", "event", "delivered_by").prefetch_related("items__variant__product", "history__actor"),
        pk=order_id,
    )
    from event.models import CreditTransaction

    credit_transactions = CreditTransaction.objects.filter(
        transaction_id__in=[f"eshop-order-{order.pk}", f"eshop-cancel-{order.pk}"]
    ).order_by("-transaction_date")

    return render(
        request,
        "eshop/admin-order-detail.html",
        {
            "order": order,
            "credit_transactions": credit_transactions,
            "history_entries": order.history.all(),
        },
    )


# ── Cart ─────────────────────────────────────────────────────────────────────

@require_POST
def add_to_cart(request):
    StockReservation.cleanup_expired()
    variant_id = request.POST.get("variant_id")
    try:
        quantity = max(1, int(request.POST.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1
    try:
        variant = get_object_or_404(ProductVariant, pk=int(variant_id), active=True)
    except (TypeError, ValueError):
        return redirect("eshop:shop")
    cart_obj = Cart(request)
    available_stock = _available_stock_for_variant(variant.pk, session_key=_ensure_session_key(request))
    current_quantity = cart_obj.get_quantity(variant.pk)
    addable_quantity = min(quantity, max(available_stock - current_quantity, 0))
    if available_stock <= 0:
        messages.warning(request, "Vybraná varianta už není skladem.")
        return redirect("eshop:product-detail", slug=variant.product.slug)
    if addable_quantity <= 0:
        messages.warning(request, "V košíku už máš maximální počet kusů, které jsou skladem.")
        return redirect("eshop:product-detail", slug=variant.product.slug)
    if addable_quantity < quantity:
        messages.warning(request, "Do košíku jsme přidali jen aktuálně dostupný počet kusů.")
    cart_obj.add(variant.pk, addable_quantity)
    _sync_stock_reservations(request, cart_obj)
    
    # HTMX podpora: pokud přidáváme z detailu, vrátíme jen aktualizovaný widget košíku
    if request.headers.get('HX-Request'):
        return render(request, "eshop/partials/cart_count.html", {
            "cart_count": len(cart_obj)
        })

    return redirect(f"{reverse('eshop:product-detail', args=[variant.product.slug])}?added=1")


def cart(request):
    StockReservation.cleanup_expired()
    cart_obj = Cart(request)
    if request.method == "POST" and request.POST.get("action") in {"remove", "update"}:
        action = request.POST.get("action")
        vid = request.POST.get("variant_id")
        if action == "remove" and vid:
            cart_obj.remove(vid)
        elif action == "update" and vid:
            try:
                qty = int(request.POST.get("quantity", 1))
            except ValueError:
                qty = 1
            variant = ProductVariant.objects.filter(pk=vid, active=True).first()
            available_stock = _available_stock_for_variant(vid, session_key=_ensure_session_key(request))
            if not variant or available_stock <= 0:
                cart_obj.remove(vid)
                messages.warning(request, "Položka už není skladem a byla z košíku odebrána.")
            else:
                if qty > available_stock:
                    qty = available_stock
                    messages.warning(request, "Počet kusů byl upraven podle aktuální skladové zásoby.")
                cart_obj.set(vid, qty)
        _sync_stock_reservations(request, cart_obj)
        
        # Pokud jde o HTMX, vracíme aktualizovaný stav (např. celý obsah košíku)
        if request.headers.get('HX-Request'):
            items, total, _ = _build_cart_items(cart_obj, normalize=True, session_key=_ensure_session_key(request))
            return render(request, "eshop/partials/cart_table.html", {"items": items, "total": total, "cart_count": len(cart_obj)})
            
        return redirect("eshop:cart")

    items, total, stock_warnings = _build_cart_items(
        cart_obj,
        normalize=True,
        session_key=_ensure_session_key(request) if cart_obj else None,
    )
    for warning in stock_warnings:
        messages.warning(request, warning)
    if not items:
        _release_stock_reservations(request)

    return render(request, "eshop/cart.html", {"items": items, "total": total})


def checkout(request):
    StockReservation.cleanup_expired()
    cart_obj = Cart(request)
    if not cart_obj:
        _release_stock_reservations(request)
        return redirect("eshop:cart")

    if request.method == "POST" and request.POST.get("action") in {"remove", "update"}:
        action = request.POST.get("action")
        vid = request.POST.get("variant_id")
        if action == "remove" and vid:
            cart_obj.remove(vid)
        elif action == "update" and vid:
            try:
                qty = int(request.POST.get("quantity", 1))
            except ValueError:
                qty = 1
            variant = ProductVariant.objects.filter(pk=vid, active=True).first()
            available_stock = _available_stock_for_variant(vid, session_key=_ensure_session_key(request))
            if not variant or available_stock <= 0:
                cart_obj.remove(vid)
                messages.warning(request, "Položka už není skladem a byla z checkoutu odebrána.")
            else:
                if qty > available_stock:
                    qty = available_stock
                    messages.warning(request, "Počet kusů byl upraven podle aktuální skladové zásoby.")
                cart_obj.set(vid, qty)
        _sync_stock_reservations(request, cart_obj)
        return redirect("eshop:checkout")

    items, total, stock_warnings = _build_cart_items(
        cart_obj,
        normalize=True,
        session_key=_ensure_session_key(request),
    )
    if not items:
        _release_stock_reservations(request)
        for warning in stock_warnings:
            messages.warning(request, warning)
        return redirect("eshop:shop")

    reservation_expires_at = _sync_stock_reservations(request, cart_obj)

    for warning in stock_warnings:
        messages.warning(request, warning)

    total_int = int(total)
    can_submit_order = bool(request.user.is_authenticated)
    checkout_credit_warning = ""
    if not request.user.is_authenticated:
        checkout_credit_warning = "Pro dokončení objednávky se nejdřív přihlas ke svému účtu s kreditem."
    elif request.user.credit < total_int:
        can_submit_order = False
        checkout_credit_warning = (
            f"Na účtu nemáš dostatek kreditu. K dispozici je {request.user.credit} Kč, "
            f"ale objednávka stojí {total_int} Kč."
        )
    pickup_events = CheckoutForm().fields["event"].queryset
    pickup_unavailable_warning = ""
    if not pickup_events.exists():
        can_submit_order = False
        pickup_unavailable_warning = (
            "Aktuálně není vypsané místo výdeje e-shop objednávek. "
            "Objednávku teď nejde dokončit, vrať se prosím později."
        )

    initial = {}
    if request.user.is_authenticated:
        u = request.user
        initial = {
            "first_name": getattr(u, "first_name", ""),
            "last_name": getattr(u, "last_name", ""),
            "email": u.email,
        }

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid() and can_submit_order:
            submitted_token = request.POST.get("checkout_token", "")
            expected_token = request.session.get("eshop_checkout_token", "")
            if not submitted_token or submitted_token != expected_token:
                messages.error(request, "Platnost checkout formuláře vypršela. Zkontroluj košík a odešli objednávku znovu.")
                return redirect("eshop:checkout")
            submit_lock_key = _checkout_submit_lock_key(request, submitted_token, cart_obj)
            if not cache.add(submit_lock_key, True, 120):
                messages.warning(request, "Objednávku už zpracováváme. Neodesílej formulář znovu.")
                return redirect("eshop:checkout")
            try:
                with db_tx.atomic():
                    order = form.save(commit=False)
                    order.user = request.user
                    order.save()
                    OrderHistory.record(
                        order=order,
                        action=OrderHistory.Action.CREATED,
                        actor=request.user,
                        note="Objednávka vytvořena z checkoutu.",
                    )
                    for item in items:
                        OrderItem.objects.create(
                            order=order,
                            variant=item["variant"],
                            quantity=item["quantity"],
                            unit_price=item["variant"].price,
                        )
                    order.charge_credits(actor=request.user)
                    order.ensure_invoice_number(actor=request.user)
            except ValueError as exc:
                cache.delete(submit_lock_key)
                messages.error(request, str(exc))
            else:
                _release_stock_reservations(request)
                cart_obj.clear()
                request.session.pop("eshop_checkout_token", None)
                request.session["last_order_id"] = order.pk
                return redirect("eshop:order-confirmation", order_id=order.pk)
        if form.is_valid() and not can_submit_order:
            messages.error(request, checkout_credit_warning or pickup_unavailable_warning)
    else:
        form = CheckoutForm(initial=initial)

    selected_pickup_event = None
    if form.is_bound and form.is_valid():
        selected_pickup_event = form.cleaned_data.get("event")
    elif form.initial.get("event"):
        selected_pickup_event = pickup_events.filter(pk=form.initial["event"]).first()

    return render(
        request,
        "eshop/checkout.html",
        {
            "form": form,
            "items": items,
            "total": total,
            "can_submit_order": can_submit_order,
            "checkout_credit_warning": checkout_credit_warning,
            "pickup_unavailable_warning": pickup_unavailable_warning,
            "selected_pickup_event": selected_pickup_event,
            "reservation_expires_at": reservation_expires_at,
            "checkout_token": _checkout_token(request),
        },
    )


def order_confirmation(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("user").prefetch_related("items__variant__product"),
        pk=order_id,
    )
    if order.is_paid and not order.invoice_number:
        order.ensure_invoice_number(actor=request.user if request.user.is_authenticated else None)

    # Allow access to session owner or the linked user
    is_session_owner = request.session.get("last_order_id") == order_id
    is_order_user = request.user.is_authenticated and order.user_id == request.user.pk
    if not is_session_owner and not is_order_user:
        raise Http404

    can_pay_credits = (
        request.user.is_authenticated
        and order.user_id == request.user.pk
        and not order.is_paid
        and request.user.credit >= int(order.total)
    )

    return render(request, "eshop/order_confirmation.html", {
        "order": order,
        "can_pay_credits": can_pay_credits,
    })


@require_POST
@login_required
def pay_with_credits(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    return redirect("eshop:order-confirmation", order_id=order_id)


@login_required
def download_invoice(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__variant__product"),
        pk=order_id,
        user=request.user,
    )
    # Always regenerate to keep the PDF aligned with the current invoice template.
    _save_invoice(order, actor=request.user)
    order.refresh_from_db(fields=["invoice_pdf"])
    if not order.invoice_pdf:
        raise Http404
    response = HttpResponse(order.invoice_pdf.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="faktura-{order.invoice_number or order.pk}.pdf"'
    return response


@login_required
def download_credit_note(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__variant__product"),
        pk=order_id,
        user=request.user,
    )
    if order.status != Order.Status.CANCELED:
        raise Http404
    _save_credit_note(order, actor=request.user)
    order.refresh_from_db(fields=["credit_note_pdf", "credit_note_number"])
    if not order.credit_note_pdf:
        raise Http404
    response = HttpResponse(order.credit_note_pdf.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="dobropis-{order.credit_note_number or order.pk}.pdf"'
    return response


@login_required
def my_orders(request):
    orders = list(
        Order.objects
        .filter(user=request.user)
        .select_related("event", "delivered_by")
        .prefetch_related("items__variant__product")
        .order_by("-created")
    )
    for order in orders:
        if order.is_paid and not order.invoice_number:
            order.ensure_invoice_number(actor=request.user)
    cancelable_count = sum(1 for order in orders if order.is_cancelable)
    return render(
        request,
        "eshop/my_orders.html",
        {
            "orders": orders,
            "order_count": len(orders),
            "paid_count": sum(1 for order in orders if order.credits_charged and order.status != Order.Status.CANCELED),
            "pending_count": sum(1 for order in orders if order.status == Order.Status.PENDING),
            "cancelable_count": cancelable_count,
        },
    )


@require_POST
@login_required
def cancel_order(request, order_id):
    order = get_object_or_404(Order.objects.prefetch_related("items__variant"), pk=order_id, user=request.user)
    try:
        order.cancel_by_user(actor=request.user)
        _save_credit_note(order, actor=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Objednávka č. {order.invoice_number or order.pk} byla stornována. Kredit jsme vrátili zpět na účet a kusy vrátili na sklad.",
        )
    return redirect("eshop:my-orders")


def size_guide(request):
    return render(request, "eshop/size_guide.html")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _save_invoice(order, *, actor=None):
    """Generate PDF invoice and attach it to order.invoice_pdf (best-effort)."""
    try:
        invoice_number = order.ensure_invoice_number(actor=actor)
        buf = generate_invoice(order)
        order.invoice_pdf.save(f"faktura-{invoice_number}.pdf", ContentFile(buf.read()), save=True)
    except Exception:
        logger.exception("Invoice PDF generation failed for e-shop order %s", order.pk)


def _save_credit_note(order, *, actor=None):
    """Generate PDF credit note and attach it to order.credit_note_pdf (best-effort)."""
    try:
        credit_note_number = order.ensure_credit_note_number(actor=actor)
        buf = generate_credit_note(order)
        order.credit_note_pdf.save(f"dobropis-{credit_note_number}.pdf", ContentFile(buf.read()), save=True)
    except Exception:
        logger.exception("Credit note PDF generation failed for e-shop order %s", order.pk)


def _ensure_session_key(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


def _active_reservations_queryset():
    now = timezone.now()
    return StockReservation.objects.filter(expires_at__gt=now)


def _reserved_quantities_by_variant(*, exclude_session_key=None):
    reservations = _active_reservations_queryset()
    if exclude_session_key:
        reservations = reservations.exclude(session_key=exclude_session_key)
    rows = reservations.values("variant_id").annotate(total_quantity=Sum("quantity"))
    return {row["variant_id"]: row["total_quantity"] for row in rows}


def _available_stock_for_variant(variant_id, *, session_key=None):
    variant = ProductVariant.objects.filter(pk=variant_id, active=True).first()
    if not variant:
        return 0
    reserved_by_others = _reserved_quantities_by_variant(exclude_session_key=session_key).get(int(variant_id), 0)
    return max(variant.stock - reserved_by_others, 0)


def _release_stock_reservations(request, *, variant_ids=None):
    if not request.session.session_key:
        return
    reservations = StockReservation.objects.filter(session_key=request.session.session_key)
    if variant_ids is not None:
        reservations = reservations.filter(variant_id__in=variant_ids)
    reservations.delete()


def _sync_stock_reservations(request, cart_obj):
    session_key = _ensure_session_key(request)
    new_expires_at = timezone.now() + timezone.timedelta(minutes=RESERVATION_MINUTES)
    variant_ids = cart_obj.variant_ids()
    StockReservation.objects.filter(session_key=session_key).exclude(variant_id__in=variant_ids).delete()
    for variant_id, quantity in cart_obj.raw().items():
        StockReservation.objects.update_or_create(
            session_key=session_key,
            variant_id=int(variant_id),
            defaults={"quantity": quantity},
            create_defaults={"quantity": quantity, "expires_at": new_expires_at},
        )
    earliest = (
        StockReservation.objects.filter(session_key=session_key)
        .order_by("expires_at")
        .values_list("expires_at", flat=True)
        .first()
    )
    return earliest or new_expires_at


def _build_cart_items(cart_obj, *, normalize=False, session_key=None):
    raw = cart_obj.raw()
    if not raw:
        return [], Decimal("0"), []
    variants_map = {
        v.pk: v
        for v in ProductVariant.objects.select_related("product").filter(pk__in=cart_obj.variant_ids(), active=True)
    }
    reserved_by_others = _reserved_quantities_by_variant(exclude_session_key=session_key)
    items = []
    total = Decimal("0")
    warnings = []
    for vid_str, qty in raw.items():
        variant_id = int(vid_str)
        variant = variants_map.get(variant_id)
        if variant is None:
            if normalize:
                cart_obj.remove(variant_id)
                warnings.append("Jedna z položek už není dostupná a byla z checkoutu odebrána.")
            continue
        available_stock = max(variant.stock - reserved_by_others.get(variant_id, 0), 0)
        if available_stock <= 0:
            if normalize:
                cart_obj.remove(variant_id)
                warnings.append(
                    f"Varianta {variant.product.name} / {variant.label} už není skladem nebo je právě rezervovaná a byla odebrána."
                )
            continue
        normalized_qty = min(qty, available_stock)
        if normalize and normalized_qty != qty:
            cart_obj.set(variant_id, normalized_qty)
            warnings.append(
                f"Počet kusů pro {variant.product.name} / {variant.label} byl upraven na aktuálně dostupné množství po započtení rezervací."
            )
        subtotal = variant.price * normalized_qty
        items.append({"variant": variant, "quantity": normalized_qty, "subtotal": subtotal})
        total += subtotal
    return items, total, warnings


def _low_stock_variants():
    return (
        ProductVariant.objects
        .select_related("product")
        .filter(active=True, stock__lte=5)
        .order_by("stock", "product__name")
    )
