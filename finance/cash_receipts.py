from decimal import Decimal, InvalidOperation
from io import BytesIO
import os
import xml.etree.ElementTree as ET

from django.core.files.base import ContentFile
from django.db.models import Max
from django.template.defaultfilters import slugify
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from event.models import Event
from finance.invoices import (
    COST_CENTER_CODE,
    FONT_BOLD_PATH,
    FONT_REGULAR_PATH,
    LOGO_PATH,
    SUPPLIER_CITY,
    SUPPLIER_COUNTRY_EN,
    SUPPLIER_ICO,
    SUPPLIER_NAME,
    SUPPLIER_STREET,
    _money,
    _register_fonts,
)
from finance.models import EventCashReceipt


class EventCashReceiptService:
    def __init__(self):
        _register_fonts()

    def _build_receipt_number(self):
        year = timezone.localdate().year
        prefix = f"{COST_CENTER_CODE}P{year}"
        used_indexes = set()
        for number in EventCashReceipt.objects.filter(number__startswith=prefix).values_list("number", flat=True):
            suffix = str(number)[len(prefix):]
            if suffix.isdigit():
                used_indexes.add(int(suffix))
        next_index = 1
        while next_index in used_indexes:
            next_index += 1
        return f"{prefix}{next_index:04d}"

    def _receipt_filename_base(self, receipt):
        event_slug = slugify(receipt.event.name) or f"event-{receipt.event_id}"
        customer_slug = slugify(receipt.customer_name) or f"receipt-{receipt.id}"
        return f"{receipt.number}-{event_slug}-{customer_slug}"

    def _subject_text(self, event):
        if event.date:
            return f"Entry fee for race {event.name} held on {event.date:%d.%m.%Y}"
        return f"Entry fee for race {event.name}"

    def _item_detail_text(self, receipt):
        details = [f"Rider: {receipt.rider_name}"]
        if receipt.uci_id:
            details.append(f"UCI ID: {receipt.uci_id}")
        if receipt.category:
            details.append(f"Class: {receipt.category}")
        return " | ".join(details)

    def _generate_pdf(self, receipt):
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        if os.path.exists(LOGO_PATH):
            pdf.drawImage(
                LOGO_PATH,
                width - 48 * mm,
                height - 28 * mm,
                width=28 * mm,
                height=18 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )

        pdf.setTitle(f"Cash receipt {receipt.number}")
        pdf.setFont("DejaVuSans-Bold", 18)
        pdf.drawString(20 * mm, height - 20 * mm, f"Cash receipt No. {receipt.number}")

        pdf.setFont("DejaVuSans", 10)
        pdf.drawString(20 * mm, height - 32 * mm, f"Issue date: {receipt.issue_date:%d.%m.%Y}")

        pdf.setFont("DejaVuSans-Bold", 11)
        pdf.drawString(20 * mm, height - 50 * mm, "Recipient")
        pdf.drawString(110 * mm, height - 50 * mm, "Customer")

        pdf.setFont("DejaVuSans", 10)
        left_y = height - 58 * mm
        for line in (
            SUPPLIER_NAME,
            SUPPLIER_STREET,
            SUPPLIER_CITY,
            SUPPLIER_COUNTRY_EN,
            f"Company ID: {SUPPLIER_ICO}",
            "We are not VAT payers",
        ):
            pdf.drawString(20 * mm, left_y, line)
            left_y -= 5 * mm

        right_y = height - 58 * mm
        payer_lines = []
        if receipt.customer_name:
            payer_lines.append(receipt.customer_name)
        if receipt.customer_street:
            payer_lines.append(receipt.customer_street)
        city_line = " ".join(part for part in [receipt.customer_zip_code, receipt.customer_city] if part).strip()
        if city_line:
            payer_lines.append(city_line)
        if receipt.customer_country:
            payer_lines.append(receipt.customer_country)
        for line in payer_lines:
            pdf.drawString(110 * mm, right_y, line)
            right_y -= 5 * mm

        subject_y = min(left_y, right_y) - 8 * mm
        pdf.setFont("DejaVuSans-Bold", 10)
        pdf.drawString(20 * mm, subject_y, "Payment purpose:")
        pdf.setFont("DejaVuSans", 10)
        subject_lines = simpleSplit(self._subject_text(receipt.event), "DejaVuSans", 10, 140 * mm)
        for index, line in enumerate(subject_lines):
            pdf.drawString(20 * mm, subject_y - 6 * mm - (index * 5 * mm), line)
        subject_bottom_y = subject_y - 6 * mm - ((len(subject_lines) - 1) * 5 * mm)

        if receipt.note:
            note_y = subject_bottom_y - 8 * mm
            pdf.drawString(20 * mm, note_y, f"Note: {receipt.note[:100]}")
            subject_bottom_y = note_y

        table_top = subject_bottom_y - 16 * mm
        pdf.setFillColor(colors.HexColor("#1E293B"))
        pdf.rect(20 * mm, table_top, 170 * mm, 8 * mm, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setFont("DejaVuSans-Bold", 9)
        pdf.drawString(24 * mm, table_top + 2.5 * mm, "Item")
        pdf.drawString(168 * mm, table_top + 2.5 * mm, "Amount")

        row_y = table_top - 7 * mm
        pdf.setFillColor(colors.black)
        pdf.setFont("DejaVuSans", 9)
        pdf.drawString(24 * mm, row_y, self._subject_text(receipt.event)[:74])
        pdf.setFont("DejaVuSans", 8)
        pdf.setFillColor(colors.HexColor("#475569"))
        pdf.drawString(24 * mm, row_y - 4.8 * mm, self._item_detail_text(receipt)[:88])
        pdf.setFillColor(colors.black)
        pdf.drawRightString(187 * mm, row_y, f"{receipt.amount:.2f} Kč")

        total_y = row_y - 18 * mm
        pdf.line(120 * mm, total_y, 190 * mm, total_y)
        total_y -= 7 * mm
        pdf.setFont("DejaVuSans-Bold", 11)
        pdf.drawString(136 * mm, total_y, "Received")
        pdf.drawRightString(187 * mm, total_y, f"{receipt.amount:.2f} Kč")

        footer_y = total_y - 18 * mm
        pdf.setFont("DejaVuSans", 9)
        pdf.drawString(20 * mm, footer_y, "This document was issued manually for a foreign rider.")
        pdf.drawRightString(width - 20 * mm, 12 * mm, "Page 1 of 1")

        pdf.showPage()
        pdf.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _build_flexibee_xml(self, receipts):
        root = ET.Element("winstrom", version="1.0")
        for receipt in receipts:
            doc = ET.SubElement(root, "pokladni-pohyb", action="create")
            ET.SubElement(doc, "kod").text = receipt.number
            ET.SubElement(doc, "typPohybuK").text = "typPohybu.prijem"
            ET.SubElement(doc, "datVyst").text = receipt.issue_date.isoformat()
            ET.SubElement(doc, "sumCelkem").text = f"{receipt.amount:.2f}"
            ET.SubElement(doc, "mena").text = "code:CZK"
            if receipt.customer_name:
                ET.SubElement(doc, "nazFirmy").text = receipt.customer_name
            if receipt.customer_street:
                ET.SubElement(doc, "ulice").text = receipt.customer_street
            if receipt.customer_city:
                ET.SubElement(doc, "mesto").text = receipt.customer_city
            if receipt.customer_zip_code:
                ET.SubElement(doc, "psc").text = receipt.customer_zip_code
            if receipt.customer_country:
                ET.SubElement(doc, "stat").text = receipt.customer_country
            description = self._subject_text(receipt.event)
            description = f"{description} - rider {receipt.rider_name}"
            if receipt.category:
                description = f"{description} - {receipt.category}"
            if receipt.uci_id:
                description = f"{description}, UCI ID {receipt.uci_id}"
            if receipt.note:
                description = f"{description}. {receipt.note}"
            ET.SubElement(doc, "popis").text = description
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _save_receipt_pdf(self, receipt):
        pdf_bytes = self._generate_pdf(receipt)
        receipt.pdf.save(f"{self._receipt_filename_base(receipt)}.pdf", ContentFile(pdf_bytes), save=False)

    def update_receipt(
        self,
        receipt,
        rider_name,
        amount,
        customer_name="",
        customer_street="",
        customer_city="",
        customer_zip_code="",
        customer_country="",
        uci_id="",
        category="",
        note="",
    ):
        receipt.customer_name = customer_name.strip()
        receipt.customer_street = customer_street.strip()
        receipt.customer_city = customer_city.strip()
        receipt.customer_zip_code = customer_zip_code.strip()
        receipt.customer_country = customer_country.strip()
        receipt.rider_name = rider_name.strip()
        receipt.uci_id = uci_id.strip()
        receipt.category = category.strip()
        receipt.note = note.strip()
        receipt.amount = _money(amount)
        self._save_receipt_pdf(receipt)
        receipt.save()
        return receipt

    def delete_receipt(self, receipt):
        if receipt.pdf:
            receipt.pdf.delete(save=False)
        receipt.delete()

    def create_receipt(
        self,
        event,
        rider_name,
        amount,
        customer_name="",
        customer_street="",
        customer_city="",
        customer_zip_code="",
        customer_country="",
        uci_id="",
        category="",
        note="",
    ):
        receipt = EventCashReceipt(
            number=self._build_receipt_number(),
            issue_date=timezone.localdate(),
            event=event,
            customer_name=customer_name.strip(),
            customer_street=customer_street.strip(),
            customer_city=customer_city.strip(),
            customer_zip_code=customer_zip_code.strip(),
            customer_country=customer_country.strip(),
            rider_name=rider_name.strip(),
            uci_id=uci_id.strip(),
            category=category.strip(),
            note=note.strip(),
            amount=_money(amount),
        )
        self._save_receipt_pdf(receipt)
        receipt.save()
        return receipt

    def export_xml_for_event(self, event):
        receipts = list(EventCashReceipt.objects.filter(event=event).order_by("number"))
        if not receipts:
            return b""
        return self._build_flexibee_xml(receipts)


def parse_receipt_amount(raw_value):
    try:
        amount = _money(Decimal(str(raw_value).replace(",", ".")))
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0:
        return None
    return amount


def create_event_cash_receipt(
    event_id,
    rider_name,
    amount,
    customer_name="",
    customer_street="",
    customer_city="",
    customer_zip_code="",
    customer_country="",
    uci_id="",
    category="",
    note="",
):
    event = Event.objects.select_related("organizer").get(pk=event_id)
    return EventCashReceiptService().create_receipt(
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
