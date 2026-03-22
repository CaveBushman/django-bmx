"""
event/views/views_pdf.py — generování PDF dokumentů

Obsah: protokol čipů (půjčovné), podklad pro fakturaci, ruční přihláška, faktura, přehled neplatných licencí.
"""

import logging
import os
import datetime
from django.http import HttpResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from event.models import Event, Entry
from event.func import invalid_licence_in_event
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.units import cm

logger = logging.getLogger(__name__)

# Shared konstanty pro PDF
FONT_REGULAR_PATH = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans.ttf")
FONT_BOLD_PATH = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans-Bold.ttf")
LOGO_PATH = os.path.join(settings.BASE_DIR, "static/images/logo.png")


def _register_fonts():
    """Zaregistruje DejaVu fonty pro ReportLab (volá se jednou na začátku view)."""
    pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_REGULAR_PATH))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", FONT_BOLD_PATH))


def _draw_logo_and_title(p, width, height, margin, title_text, subtitle_text):
    """Vykreslí logo, název závodu a nadpis protokolu (společný kód pro PDF views)."""
    # Logo vpravo nahoře
    if os.path.exists(LOGO_PATH):
        p.drawImage(
            LOGO_PATH,
            width - margin - 75, height - margin - 15,
            width=100, height=50, preserveAspectRatio=True, mask="auto",
        )
    # Název závodu vlevo nahoře
    p.setFont("DejaVuSans", 12)
    p.drawString(margin, height - margin, title_text)
    # Nadpis uprostřed
    p.setFont("DejaVuSans-Bold", 18)
    p.drawCentredString(width / 2, height - margin - 30, subtitle_text)
    p.line(margin, height - margin - 35, width - margin, height - margin - 35)


def _draw_table_page(p, data, header, col_widths, margin, width, height, total_pages,
                     start_row, current_page, rows_per_page, top_offset=60, draw_footer=True):
    """Vykreslí jednu stránku tabulky s paginací (rekurzivní pro víc stránek)."""
    page_data = data[start_row:start_row + rows_per_page]
    if start_row > 0:
        page_data = [header] + page_data  # Hlavička na každé stránce

    table = Table(page_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]))

    table_width, table_height = table.wrap(0, 0)
    table.drawOn(p, margin, height - margin - top_offset - table_height)

    if draw_footer:
        # Číslo stránky vpravo dole
        p.setFont("DejaVuSans", 10)
        p.drawRightString(width - margin - 10, margin + 10, f"Stránka {current_page} z {total_pages}")
        # Datum tisku vlevo dole
        current_date = datetime.datetime.now().strftime("%d.%m.%Y")
        p.drawString(margin, margin + 10, f"VYTIŠTĚNO DNE: {current_date}")

    if start_row + rows_per_page < len(data):
        p.showPage()
        _draw_table_page(p, data, header, col_widths, margin, width, height, total_pages,
                         start_row + rows_per_page, current_page + 1, rows_per_page, top_offset, draw_footer)


def generate_pdf(request, pk):
    """Protokol pro půjčení čipů — jezdci bez vlastního transpondéru.

    Formát: A4 na šířku, tabulka s jezdci, zálohou a kolonkami pro předání/vrácení.
    """
    try:
        event = Event.objects.get(pk=pk)
    except Event.DoesNotExist:
        return HttpResponse("Event not found", status=404)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="protokol_cipy.pdf"'

    p = canvas.Canvas(response, pagesize=landscape(A4))
    width, height = landscape(A4)
    margin = 2 * cm
    content_width = width - 2 * margin

    _register_fonts()
    _draw_logo_and_title(p, width, height, margin, event.name.upper(), "PROTOKOL – ČIPY K PŮJČENÍ")

    # Jezdci bez transpondéru přihlášení na závod
    entries = Entry.objects.filter(
        event=pk, payment_complete=True,
        rider__transponder_20__isnull=True, rider__transponder_24__isnull=True,
        is_beginner=False,
    ).order_by("rider__last_name", "rider__first_name")

    header = ["JEZDEC", "ČÍSLO", "KATEGORIE", "KLUB", "ZÁLOHA", "ČIP", "PŘED.", "VRÁC."]
    data = [header]
    for entry in entries:
        category = entry.rider.class_20 if entry.is_20 else entry.rider.class_24 if entry.is_24 else ""
        data.append([
            f"{entry.rider.last_name} {entry.rider.first_name}",
            entry.rider.plate_display if entry.rider else "",
            category,
            entry.rider.club or "",
            "", "",  # záloha, čip — vyplní komisař ručně
            "☐", "☐",  # předáno, vráceno
        ])

    # Prázdné řádky na konci pro ruční doplnění
    for _ in range(9):
        data.append(["", "", "", "", "", "", "☐", "☐"])

    col_widths = [
        content_width * 0.30, content_width * 0.12, content_width * 0.12,
        content_width * 0.18, content_width * 0.08, content_width * 0.08,
        content_width * 0.05, content_width * 0.05,
    ]
    rows_per_page = 10
    total_pages = max(1, (len(data) - 1 + rows_per_page - 1) // rows_per_page)

    _draw_table_page(p, data, header, col_widths, margin, width, height,
                     total_pages, 0, 1, rows_per_page)

    p.showPage()
    p.save()
    return response


def generate_invoice_preparation_pdf(request, pk):
    """Podklad pro fakturaci — prázdná tabulka s kolonkami pro zaplacení.

    Formát: A4 na výšku, 16 prázdných řádků.
    """
    event = Event.objects.get(pk=pk)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="podklad_pro_fakturaci.pdf"'

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin = 2 * cm
    content_width = width - 2 * margin

    _register_fonts()
    event_date = event.date.strftime("%d.%m.%Y")
    _draw_logo_and_title(p, width, height, margin,
                         f"{event_date} - {event.name.upper()}", "PODKLAD PRO FAKTURACI")

    header = ["JEZDEC A ST. ČÍSLO", "ČIP", "KLUB", "FAKTURA", "HOTOVOST"]
    data = [header] + [["", "", "", "☐", "☐"] for _ in range(16)]

    col_widths = [
        content_width * 0.30, content_width * 0.12,
        content_width * 0.30, content_width * 0.15, content_width * 0.15,
    ]
    rows_per_page = 17
    total_pages = max(1, (len(data) - 1 + rows_per_page - 1) // rows_per_page)

    _draw_table_page(p, data, header, col_widths, margin, width, height,
                     total_pages, 0, 1, rows_per_page)

    p.showPage()
    p.save()
    return response


@login_required(login_url="/login/")
@staff_member_required
def generate_manual_entry_form_pdf(request, pk):
    """Prázdný formulář pro ruční přihlášku jezdců na místě.

    Formát: A4 na šířku, jedna stránka.
    """
    try:
        event = Event.objects.get(pk=pk)
    except Event.DoesNotExist:
        return HttpResponse("Event not found", status=404)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="manual-entry-form.pdf"'

    p = canvas.Canvas(response, pagesize=landscape(A4))
    width, height = landscape(A4)
    margin = 2 * cm
    content_width = width - 2 * margin

    _register_fonts()
    event_date = event.date.strftime("%d.%m.%Y") if event.date else ""
    _draw_logo_and_title(
        p,
        width,
        height,
        margin,
        f"{event.name.upper()} | {event_date}",
        "RUČNÍ PŘIHLÁŠKA",
    )

    p.setFont("DejaVuSans", 10)
    p.setFillColor(colors.HexColor("#475569"))
    p.drawString(
        margin,
        height - margin - 52,
        "Vyplň ručně: startovní číslo, jméno a příjmení, UCI ID, kategorii a potvrzení o úhradě startovného.",
    )

    header = ["START. Č.", "JMÉNO A PŘÍJMENÍ", "UCI ID", "KATEGORIE", "ČIP", "UHRAZENO"]
    data = [header] + [["", "", "", "", "", "☐"] for _ in range(11)]

    col_widths = [
        content_width * 0.11,
        content_width * 0.31,
        content_width * 0.16,
        content_width * 0.18,
        content_width * 0.10,
        content_width * 0.14,
    ]
    rows_per_page = len(data)
    total_pages = 1

    _draw_table_page(
        p,
        data,
        header,
        col_widths,
        margin,
        width,
        height,
        total_pages,
        0,
        1,
        rows_per_page,
        top_offset=78,
        draw_footer=False,
    )

    p.save()
    return response


def invoice_view(request, pk):
    """Generování faktury ve formátu PDF.

    Zatím používá pevná testovací data — TODO: napojit na skutečná data z DB.
    """
    # TODO: nahradit testovací data skutečnými daty z DB podle pk
    invoice_data = {
        "number": "20240001",
        "issue_date": "02.01.2024",
        "due_date": "09.01.2024",
        "payment_method": "Převodem",
        "vs": "20240001",
        "iban": "CZ32 0300 0000 0000 5051 1001",
        "supplier": [
            "Adventure Land s.r.o.", "Křenova 438/7", "162 00 Praha",
            "IČ: 25747908", "DIČ: CZ25747908",
        ],
        "customer": [
            "PROMAFIX s.r.o.", "Semčice 96", "294 46 Semčice",
            "IČ: 08554625", "DIČ: CZ08554625",
        ],
        "items": [
            {"description": "Rallye test - pronájem okruhu, zabezpečení TK, Com",
             "qty": 5, "unit_price": 3990.00, "vat": 21, "total": 24139.50},
            {"description": "Zaokrouhlení",
             "qty": 1, "unit_price": 0.50, "vat": 0, "total": 0.50},
        ],
        "summary": {"base": 19950.00, "vat": 4189.50, "total": 24140.00},
    }

    # TODO: implementovat generate_invoice_pdf v event/credit.py
    raise NotImplementedError("generate_invoice_pdf není ještě implementováno")
    pdf_buffer = None
    return HttpResponse(
        pdf_buffer,
        content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="faktura_{invoice_data["number"]}.pdf"'},
    )


@login_required(login_url="/login")
@staff_member_required
def invalid_licences_pdf(request, pk):
    """PDF seznam přihlášených jezdců s neplatnou licencí."""
    event = Event.objects.get(pk=pk)
    riders = sorted(
        invalid_licence_in_event(event),
        key=lambda rider: ((rider.last_name or "").lower(), (rider.first_name or "").lower()),
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="neplatne-licence-{event.id}.pdf"'

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin = 2 * cm
    content_width = width - 2 * margin

    _register_fonts()
    event_date = event.date.strftime("%d.%m.%Y") if event.date else "-"
    _draw_logo_and_title(
        p,
        width,
        height,
        margin,
        f"{event_date} - {event.name.upper()}",
        "JEZDCI S NEPLATNOU LICENCÍ",
    )

    p.setFont("DejaVuSans", 10)
    p.drawString(margin, height - margin - 52, f"Pořadatel: {event.organizer.team_name if event.organizer else '-'}")
    p.drawString(margin, height - margin - 68, f"Počet jezdců: {len(riders)}")

    header = ["Příjmení a jméno", "UCI ID", "Licence", "Klub"]
    data = [header]
    for rider in riders:
        data.append([
            f"{rider.last_name} {rider.first_name}",
            rider.uci_id or "",
            rider.licence or "",
            rider.club.team_name if rider.club else "",
        ])

    if len(data) == 1:
        data.append(["Žádný jezdec s neplatnou licencí", "", "", ""])

    col_widths = [
        content_width * 0.34,
        content_width * 0.20,
        content_width * 0.20,
        content_width * 0.26,
    ]
    rows_per_page = 18
    total_pages = max(1, (len(data) - 1 + rows_per_page - 1) // rows_per_page)

    _draw_table_page(
        p,
        data,
        header,
        col_widths,
        margin,
        width,
        height,
        total_pages,
        0,
        1,
        rows_per_page,
        top_offset=92,
    )

    p.showPage()
    p.save()
    return response
