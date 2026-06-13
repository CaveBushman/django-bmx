"""
event/views/views_entry.py — přihlašování jezdců na závody

Obsah: výběr jezdců, potvrzení košíku, Stripe checkout flow pro přihlášky,
       přehled přihlášených, zahraniční jezdci, poplatky po klubech.
"""

import json
import logging
from decimal import Decimal, InvalidOperation
from django.shortcuts import get_object_or_404, render, redirect
from django.http import FileResponse, HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.conf import settings
from event.models import Event, EventType, Entry, EntryForeign
from event.func import update_cart
from event.services.checkout_sessions import (
    create_entry_checkout_session,
    create_foreign_entry_checkout_session,
)
from finance.cash_receipts import EventCashReceiptService, parse_receipt_amount
from finance.invoices import (
    EventInvoiceService,
    delete_invoice_override,
    generate_event_invoices,
    save_invoice_override,
    send_event_invoices,
)
from finance.models import EventCashReceipt, EventInvoice
from event.views.entry_helpers import (
    annotate_riders_for_event,
    build_foreign_entry_summary,
    build_foreign_entry_summary_from_payload,
    build_public_entry_rows,
    calculate_selected_fee,
    collect_fees_by_club,
    enrich_foreign_summary_rows,
    get_active_riders,
    hydrate_checkout_riders,
    is_event_open_for_entries,
    load_checkout_session_payload,
    load_foreign_rider_response,
    resolve_event_beginner_support,
    split_selected_riders,
    store_selected_entries,
    sync_paid_foreign_riders,
    validate_foreign_summary_payload,
)
from event.views.payment_helpers import finalize_entry_checkout_session
import stripe

from bmx.observability import set_tag, start_span

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


def _redirect_european_cup_registration(event):
    if event.type_for_ranking == EventType.EVROPSKY_POHAR and event.uec_link:
        return redirect(event.uec_link)
    return None


@login_required(login_url="/event/not-reg")
def add_entries_view(request, pk):
    """Hlavní přihlašovací stránka — výběr jezdců a kategorií.

    GET: Zobrazí seznam aktivních jezdců s jejich kategoriemi a stavem registrace.
    POST: Zpracuje výběr checkboxů, spočítá startovné a uloží přihlášky do košíku.
    """
    event = get_object_or_404(Event.objects.select_related("classes_and_fees_like"), id=pk)
    set_tag("event.id", event.id)
    set_tag("event.name", event.name)
    set_tag("user.id", getattr(request.user, "id", None))
    registration_redirect = _redirect_european_cup_registration(event)
    if registration_redirect:
        return registration_redirect
    update_cart(request)
    beginners_enabled = resolve_event_beginner_support(event)
    riders = get_active_riders()

    if not is_event_open_for_entries(event):
        return render(request, "event/reg-close.html")

    if request.method == "POST":
        riders_beginner, riders_20, riders_24 = split_selected_riders(request, event)
        total_fee = calculate_selected_fee(event, riders_beginner, riders_20, riders_24)

        if "btn_add" in request.POST:
            store_selected_entries(request, event, riders_beginner, riders_20, riders_24)
            audit_logger.info(
                "entry_cart_updated user_id=%s event_id=%s beginner=%s class20=%s class24=%s total_fee=%s",
                request.user.id,
                event.id,
                len(riders_beginner),
                len(riders_20),
                len(riders_24),
                total_fee,
            )
            update_cart(request)
            return redirect("event:events")

        data = {
            "event": event,
            "riders_beginner": riders_beginner,
            "riders_20": riders_20,
            "riders_24": riders_24,
            "sum_fee": total_fee,
        }
        return render(request, "event/checkout.html", data)

    annotate_riders_for_event(event, riders, beginners_enabled)
    data = {
        "event": event,
        "riders": riders,
        "sum_fee": 0,
        "beginners_enabled": beginners_enabled,
    }
    return render(request, "event/entry.html", data)


def entry_riders_view(request, pk):
    """Přehled přihlášených jezdců na závod (veřejný, bez přihlášení)."""
    event = get_object_or_404(Event.objects.select_related("classes_and_fees_like"), id=pk)
    czech_entries = (
        Entry.objects.filter(event=pk, payment_complete=1, checkout=0)
        .select_related("rider", "rider__club")
    )
    foreign_entries = EntryForeign.objects.filter(event=pk, payment_complete=1, checkout=0).select_related("rider")

    czech_checkout = (
        Entry.objects.filter(event=pk, payment_complete=1, checkout=1)
        .select_related("rider", "rider__club")
    )
    foreign_checkout = EntryForeign.objects.filter(event=pk, payment_complete=1, checkout=1).select_related("rider")

    entries = build_public_entry_rows(czech_entries) + build_public_entry_rows(
        foreign_entries,
        is_foreign=True,
    )
    checkout = build_public_entry_rows(czech_checkout) + build_public_entry_rows(
        foreign_checkout,
        is_foreign=True,
    )

    entries.sort(key=lambda item: (item.last_name, item.first_name, item.category))
    checkout.sort(key=lambda item: (item.last_name, item.first_name, item.category))
    categories = sorted({entry.category for entry in entries if entry.category})

    data = {
        "event": event,
        "entries": entries,
        "checkout": checkout,
        "categories": categories,
    }
    return render(request, "event/entry-list.html", data)


def confirm_view(request):
    """Potvrzení košíku — vytvoří Stripe Checkout session pro přihlášky ze session.

    Přihlášky jsou uloženy v session jako JSON (riders_beginner, riders_20, riders_24).
    Po vytvoření Stripe session jsou Entry záznamy atomicky zapsány do DB.
    """
    event, riders_beginner, riders_20, riders_24 = load_checkout_session_payload(request)
    set_tag("event.id", event.id)
    set_tag("event.name", event.name)
    set_tag("user.id", getattr(request.user, "id", None))

    if request.method == "POST":
        total_selected = len(riders_beginner) + len(riders_20) + len(riders_24)

        try:
            with start_span(
                op="event.checkout",
                name="create_entry_checkout_session",
                event_id=event.id,
                beginner_count=len(riders_beginner),
                class20_count=len(riders_20),
                class24_count=len(riders_24),
            ):
                checkout_session = create_entry_checkout_session(
                    event=event,
                    riders_beginner=riders_beginner,
                    riders_20=riders_20,
                    riders_24=riders_24,
                )

            audit_logger.info(
                "event_checkout_started user_id=%s event_id=%s beginner=%s class20=%s class24=%s total_entries=%s session_id=%s",
                request.user.id if request.user.is_authenticated else None,
                event.id,
                len(riders_beginner),
                len(riders_20),
                len(riders_24),
                total_selected,
                checkout_session.id,
            )
            return JsonResponse({"id": checkout_session.id})
        except (stripe.error.StripeError, DatabaseError) as error:
            audit_logger.exception(
                "event_checkout_failed user_id=%s event_id=%s beginner=%s class20=%s class24=%s",
                request.user.id if request.user.is_authenticated else None,
                event.id,
                len(riders_beginner),
                len(riders_20),
                len(riders_24),
            )
            return JsonResponse({"error": str(error)}, status=403)

    hydrated_riders_beginner = hydrate_checkout_riders(event, riders_beginner, is_beginner=True)
    hydrated_riders_20 = hydrate_checkout_riders(event, riders_20, is_20=True)
    hydrated_riders_24 = hydrate_checkout_riders(event, riders_24, is_24=True)
    total_fee = calculate_selected_fee(
        event,
        hydrated_riders_beginner,
        hydrated_riders_20,
        hydrated_riders_24,
    )
    return render(
        request,
        "event/checkout.html",
        {
            "event": event,
            "riders_beginner": hydrated_riders_beginner,
            "riders_20": hydrated_riders_20,
            "riders_24": hydrated_riders_24,
            "sum_fee": total_fee,
        },
    )


def entry_foreign_view(request, pk):
    """Přihláška zahraničního jezdce (formulář)."""
    event = get_object_or_404(Event.objects.select_related("classes_and_fees_like"), pk=pk)
    registration_redirect = _redirect_european_cup_registration(event)
    if registration_redirect:
        return registration_redirect
    initial_payload = build_foreign_entry_summary_from_payload(request) or {"customer_email": "", "rows": []}
    return render(
        request,
        "event/entry-foreign.html",
        {
            "event": event,
            "initial_rows": initial_payload["rows"],
            "initial_customer_email": initial_payload["customer_email"],
        },
    )


def entry_foreign_summary_view(request, pk):
    """Rekapitulace zahraniční přihlášky před odesláním."""
    event = get_object_or_404(Event.objects.select_related("classes_and_fees_like"), pk=pk)
    registration_redirect = _redirect_european_cup_registration(event)
    if registration_redirect:
        return registration_redirect
    summary_payload = build_foreign_entry_summary_from_payload(request) or build_foreign_entry_summary(request)
    if not validate_foreign_summary_payload(summary_payload):
        return redirect("event:entry-foreign", pk=pk)
    summary_rows, total_fee = enrich_foreign_summary_rows(event, summary_payload["rows"])
    normalized_payload = {
        "customer_email": summary_payload.get("customer_email", ""),
        "rows": summary_rows,
    }
    request.session["foreign_summary_payload"] = json.dumps(normalized_payload)
    return render(
        request,
        "event/entry-foreign-summary.html",
        {
            "event": event,
            "summary_rows": summary_rows,
            "total_fee": total_fee,
            "customer_email": summary_payload.get("customer_email", ""),
            "summary_payload": json.dumps(normalized_payload),
        },
    )


def entry_foreign_pay_view(request, pk):
    """Vytvoří Stripe checkout pro zahraniční přihlášky."""
    if request.method != "POST":
        return redirect("event:entry-foreign", pk=pk)

    event = get_object_or_404(Event.objects.select_related("classes_and_fees_like"), pk=pk)
    set_tag("event.id", event.id)
    set_tag("event.name", event.name)
    registration_redirect = _redirect_european_cup_registration(event)
    if registration_redirect:
        return registration_redirect
    payload = build_foreign_entry_summary_from_payload(request)
    if not payload:
        return redirect("event:entry-foreign", pk=pk)
    if not validate_foreign_summary_payload(payload):
        return redirect("event:entry-foreign", pk=pk)

    summary_rows, total_fee = enrich_foreign_summary_rows(event, payload["rows"])
    customer_email = payload.get("customer_email", "").strip()
    if not customer_email or total_fee <= 0:
        return redirect("event:entry-foreign-summary", pk=pk)

    try:
        with start_span(
            op="event.checkout",
            name="create_foreign_entry_checkout_session",
            event_id=event.id,
            row_count=len(summary_rows),
            total_fee=str(total_fee),
        ):
            checkout_session = create_foreign_entry_checkout_session(
                event=event,
                summary_rows=summary_rows,
                customer_email=customer_email,
            )
        audit_logger.info(
            "foreign_entry_checkout_started event_id=%s rows=%s total_fee=%s customer_email=%s session_id=%s",
            event.id,
            len(summary_rows),
            total_fee,
            customer_email,
            checkout_session.id,
        )
        response = HttpResponse(status=303)
        response["Location"] = checkout_session.url
        return response
    except (stripe.error.StripeError, DatabaseError) as error:
        audit_logger.exception(
            "foreign_entry_checkout_failed event_id=%s rows=%s customer_email=%s",
            event.id,
            len(summary_rows),
            customer_email,
        )
        return JsonResponse({"error": str(error)}, status=403)


def entry_foreign_success_view(request, pk):
    """Stripe success redirect pro zahraniční přihlášky."""
    event = get_object_or_404(Event.objects.select_related("classes_and_fees_like"), pk=pk)
    registration_redirect = _redirect_european_cup_registration(event)
    if registration_redirect:
        return registration_redirect
    session_id = request.GET.get("session_id", "")
    if session_id:
        try:
            finalize_entry_checkout_session(
                session_id,
                event_id=event.id,
                is_foreign=True,
            )
            sync_paid_foreign_riders(event, session_id)
            request.session.pop("foreign_summary_payload", None)
        except (stripe.error.StripeError, DatabaseError) as error:
            logger.exception("Chyba při potvrzení foreign Stripe platby %s: %s", session_id, error)

    return render(
        request,
        "event/entry-foreign-success.html",
        {"event": event},
    )


def check_rider(request):
    """AJAX endpoint — vrátí data zahraničního jezdce podle UCI ID."""
    return load_foreign_rider_response(request)


@login_required(login_url="/login/")
@staff_member_required
def fees_on_event(request, pk):
    """Přehled startovného na závodě rozdělený po klubech."""
    event = get_object_or_404(Event, pk=pk)
    set_tag("event.id", event.id)
    set_tag("event.name", event.name)
    set_tag("user.id", getattr(request.user, "id", None))

    if request.method == "POST":
        if "btn-generate-invoices" in request.POST:
            with start_span(
                op="finance.invoice",
                name="generate_event_invoices",
                event_id=event.id,
            ):
                result = generate_event_invoices(event.id)
            if result["generated"]:
                messages.success(request, f"Vygenerováno {len(result['generated'])} faktur. Teď je můžeš upravit a následně odeslat.")
            else:
                messages.warning(request, "Pro tento závod nebyly nalezeny žádné uhrazené registrace klubů k fakturaci.")
            return redirect("event:fees-on-event", pk=pk)

        if "btn-send-invoices" in request.POST:
            with start_span(
                op="finance.invoice",
                name="send_event_invoices",
                event_id=event.id,
            ):
                result = send_event_invoices(event.id)
            if result["generated"]:
                messages.success(
                    request,
                    (
                        f"Odesláno {len(result['sent'])} e-mailů, "
                        f"bez e-mailu zůstalo {len(result['skipped'])} klubů."
                    ),
                )
            else:
                messages.warning(request, "Nejprve je potřeba faktury vygenerovat.")
            return redirect("event:fees-on-event", pk=pk)

    data = {
        "clubs": collect_fees_by_club(event),
        "event": event,
        "invoices": EventInvoice.objects.filter(event=event).select_related("club").order_by("club__team_name"),
    }
    return render(request, "event/fees-on-event.html", data)


@login_required(login_url="/login/")
@staff_member_required
def invoice_edit_view(request, pk, club_id):
    event = get_object_or_404(Event, pk=pk)
    set_tag("event.id", event.id)
    set_tag("event.name", event.name)
    set_tag("club.id", club_id)
    set_tag("user.id", getattr(request.user, "id", None))
    invoice_service = EventInvoiceService()
    with start_span(
        op="finance.invoice",
        name="invoice_preview_lookup",
        event_id=event.id,
        club_id=club_id,
    ):
        preview = next((item for item in invoice_service.get_club_previews(event) if item["club"].id == club_id), None)
    if not preview:
        messages.error(request, "Pro tento klub nejsou připravené položky faktury.")
        return redirect("event:fees-on-event", pk=pk)

    if request.method == "POST":
        if "btn_reset_defaults" in request.POST:
            delete_invoice_override(event, preview["club"])
            messages.success(request, f"Výchozí položky faktury pro klub {preview['club'].team_name} byly obnoveny.")
            return redirect("event:invoice-edit", pk=pk, club_id=club_id)

        descriptions = request.POST.getlist("description")
        amounts = request.POST.getlist("amount")
        cleaned_rows = []
        for description, amount in zip(descriptions, amounts):
            normalized_description = description.strip()
            normalized_amount = amount.strip().replace(",", ".")
            if not normalized_description and not normalized_amount:
                continue
            if not normalized_description or not normalized_amount:
                messages.error(request, "Každá položka faktury musí mít vyplněný název i částku.")
                break
            try:
                Decimal(normalized_amount)
            except (InvalidOperation, ValueError):
                messages.error(request, f'Částka "{amount}" není ve správném formátu.')
                break
            cleaned_rows.append((normalized_description, normalized_amount))
        else:
            if not cleaned_rows:
                messages.error(request, "Faktura musí obsahovat alespoň jednu položku.")
            else:
                with start_span(
                    op="finance.invoice",
                    name="save_invoice_override",
                    event_id=event.id,
                    club_id=preview["club"].id,
                    row_count=len(cleaned_rows),
                ):
                    save_invoice_override(
                        event,
                        preview["club"],
                        "\n".join(description for description, _ in cleaned_rows),
                        "\n".join(amount for _, amount in cleaned_rows),
                    )
                messages.success(request, f"Položky faktury pro klub {preview['club'].team_name} byly upraveny a PDF/XML byly přegenerovány.")
                return redirect("event:fees-on-event", pk=pk)

    return render(
        request,
        "event/invoice-edit.html",
        {
            "event": event,
            "preview": preview,
        },
    )


@login_required(login_url="/login/")
@staff_member_required
def invoice_delete_view(request, pk, invoice_id):
    if request.method != "POST":
        return redirect("event:fees-on-event", pk=pk)

    event = get_object_or_404(Event, pk=pk)
    invoice = get_object_or_404(EventInvoice, pk=invoice_id, event=event)
    EventInvoiceService().delete_invoice(invoice)
    messages.success(request, f"Faktura {invoice.number} byla smazána.")
    return redirect("event:fees-on-event", pk=pk)


@login_required(login_url="/login/")
@staff_member_required
def cash_receipts_on_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    receipt_service = EventCashReceiptService()

    if request.method == "POST":
        customer_name = request.POST.get("customer_name", "").strip()
        customer_street = request.POST.get("customer_street", "").strip()
        customer_city = request.POST.get("customer_city", "").strip()
        customer_zip_code = request.POST.get("customer_zip_code", "").strip()
        customer_country = request.POST.get("customer_country", "").strip()
        rider_name = request.POST.get("rider_name", "").strip()
        amount = parse_receipt_amount(request.POST.get("amount", ""))
        uci_id = request.POST.get("uci_id", "")
        category = request.POST.get("category", "")
        note = request.POST.get("note", "")

        if not rider_name:
            messages.error(request, "Jméno jezdce je povinné.")
        elif amount is None:
            messages.error(request, "Částka musí být číslo větší než 0.")
        else:
            receipt = receipt_service.create_receipt(
                event,
                rider_name=rider_name,
                amount=amount,
                customer_name=customer_name,
                customer_street=customer_street,
                customer_city=customer_city,
                customer_zip_code=customer_zip_code,
                customer_country=customer_country,
                uci_id=uci_id,
                category=category,
                note=note,
            )
            messages.success(request, f"Pokladní doklad {receipt.number} byl vytvořen a PDF bylo vygenerováno.")
            return redirect("event:cash-receipts-on-event", pk=pk)

    return render(
        request,
        "event/cash-receipts-on-event.html",
        {
            "event": event,
            "receipts": EventCashReceipt.objects.filter(event=event).order_by("-issue_date", "-created"),
        },
    )


@login_required(login_url="/login/")
@staff_member_required
def cash_receipts_export_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    set_tag("event.id", event.id)
    set_tag("event.name", event.name)
    set_tag("user.id", getattr(request.user, "id", None))
    with start_span(
        op="finance.cash_receipt",
        name="export_cash_receipts_xml",
        event_id=event.id,
    ):
        xml_bytes = EventCashReceiptService().export_xml_for_event(event)
    if not xml_bytes:
        messages.warning(request, "Pro tento závod zatím nejsou žádné pokladní doklady k exportu.")
        return redirect("event:cash-receipts-on-event", pk=pk)

    filename = f"cash-receipts-{event.id}.xml"
    response = HttpResponse(xml_bytes, content_type="application/xml")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required(login_url="/login/")
@staff_member_required
def cash_receipt_pdf_view(request, pk, receipt_id):
    event = get_object_or_404(Event, pk=pk)
    receipt = get_object_or_404(EventCashReceipt, pk=receipt_id, event=event)
    language = request.GET.get("lang", "en").lower()
    if language not in {"cs", "en"}:
        language = "en"

    receipt_service = EventCashReceiptService()
    if language == "en":
        receipt_service._save_receipt_pdf(receipt, language="en")
        receipt.save(update_fields=["pdf", "updated"])
        if not receipt.pdf:
            messages.error(request, "PDF pokladního dokladu se nepodařilo vygenerovat.")
            return redirect("event:cash-receipts-on-event", pk=pk)
        receipt.pdf.open("rb")
        response = FileResponse(receipt.pdf, as_attachment=True, filename=f"{receipt.number}-EN.pdf")
        return response

    pdf_bytes = receipt_service._generate_pdf(receipt, language="cs")
    if not pdf_bytes:
        messages.error(request, "PDF pokladního dokladu se nepodařilo vygenerovat.")
        return redirect("event:cash-receipts-on-event", pk=pk)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{receipt.number}-CZ.pdf"'
    return response


@login_required(login_url="/login/")
@staff_member_required
def cash_receipt_edit_view(request, pk, receipt_id):
    event = get_object_or_404(Event, pk=pk)
    receipt = get_object_or_404(EventCashReceipt, pk=receipt_id, event=event)
    receipt_service = EventCashReceiptService()

    if request.method == "POST":
        customer_name = request.POST.get("customer_name", "").strip()
        customer_street = request.POST.get("customer_street", "").strip()
        customer_city = request.POST.get("customer_city", "").strip()
        customer_zip_code = request.POST.get("customer_zip_code", "").strip()
        customer_country = request.POST.get("customer_country", "").strip()
        rider_name = request.POST.get("rider_name", "").strip()
        amount = parse_receipt_amount(request.POST.get("amount", ""))
        uci_id = request.POST.get("uci_id", "").strip()
        category = request.POST.get("category", "").strip()
        note = request.POST.get("note", "").strip()

        if not rider_name:
            messages.error(request, "Jméno jezdce je povinné.")
        elif amount is None:
            messages.error(request, "Částka musí být číslo větší než 0.")
        else:
            receipt_service.update_receipt(
                receipt,
                rider_name=rider_name,
                amount=amount,
                customer_name=customer_name,
                customer_street=customer_street,
                customer_city=customer_city,
                customer_zip_code=customer_zip_code,
                customer_country=customer_country,
                uci_id=uci_id,
                category=category,
                note=note,
            )
            messages.success(request, f"Pokladní doklad {receipt.number} byl upraven a PDF bylo přegenerováno.")
            return redirect("event:cash-receipts-on-event", pk=pk)

    return render(
        request,
        "event/cash-receipt-edit.html",
        {
            "event": event,
            "receipt": receipt,
        },
    )


@login_required(login_url="/login/")
@staff_member_required
def cash_receipt_delete_view(request, pk, receipt_id):
    if request.method != "POST":
        return redirect("event:cash-receipts-on-event", pk=pk)

    event = get_object_or_404(Event, pk=pk)
    receipt = get_object_or_404(EventCashReceipt, pk=receipt_id, event=event)
    EventCashReceiptService().delete_receipt(receipt)
    messages.success(request, f"Pokladní doklad {receipt.number} byl smazán.")
    return redirect("event:cash-receipts-on-event", pk=pk)
