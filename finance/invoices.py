from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
import os
import uuid
import xml.etree.ElementTree as ET

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction
from django.template.defaultfilters import slugify
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

try:
    import pikepdf
except ImportError:
    pikepdf = None

from event.models import Entry, Event
from finance.models import EventInvoice, EventInvoiceOverride


FONT_REGULAR_PATH = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans.ttf")
FONT_BOLD_PATH = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans-Bold.ttf")
LOGO_PATH = os.path.join(settings.BASE_DIR, "static/images/logo.png")
ISDOC_SEAL_PATH = os.path.join(settings.BASE_DIR, "static/images/ISDOC.jpeg")
SUPPLIER_NAME = "Asociace klubů BMX, z.s."
SUPPLIER_STREET = "Korunní 972/75, Vinohrady"
SUPPLIER_CITY = "130 00 Praha 3"
SUPPLIER_COUNTRY = "Česká republika"
SUPPLIER_COUNTRY_EN = "Czech Republic"
SUPPLIER_ICO = "07197896"
COST_CENTER_CODE = "001"
ISDOC_NS = "http://isdoc.cz/namespace/2013"
SCHEMA_INSTANCE_NS = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("", ISDOC_NS)
ET.register_namespace("xsi", SCHEMA_INSTANCE_NS)


def _register_fonts():
    pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_REGULAR_PATH))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", FONT_BOLD_PATH))


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"))


@dataclass
class InvoiceLine:
    description: str
    quantity: int
    unit_price: Decimal

    @property
    def total(self):
        return _money(self.quantity * self.unit_price)


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        self._saved_page_states.append(dict(self.__dict__))
        page_count = len(self._saved_page_states)
        for page_number, state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(state)
            self._draw_page_number(page_number, page_count)
            super().showPage()
        super().save()

    def _draw_page_number(self, page_number, page_count):
        width, _ = A4
        self.setFont("DejaVuSans", 9)
        self.drawRightString(width - 20 * mm, 12 * mm, f"Stránka {page_number} z {page_count}")


def draw_pdf_footer(pdf, *, left_text="", right_text=""):
    width, _ = A4
    footer_y = 16 * mm
    pdf.setStrokeColor(colors.HexColor("#CBD5E1"))
    pdf.line(20 * mm, footer_y + 4 * mm, width - 20 * mm, footer_y + 4 * mm)
    pdf.setFillColor(colors.HexColor("#64748B"))
    pdf.setFont("DejaVuSans", 8)
    if left_text:
        pdf.drawString(20 * mm, footer_y, left_text)
    if right_text:
        pdf.drawRightString(width - 20 * mm, footer_y, right_text)


class EventInvoiceService:
    def __init__(self):
        _register_fonts()

    def _build_invoice_number(self):
        year = timezone.localdate().year
        prefix = f"{COST_CENTER_CODE}{year}"
        used_indexes = set()
        for number in EventInvoice.objects.filter(number__startswith=prefix).values_list("number", flat=True):
            suffix = str(number)[len(prefix):]
            if suffix.isdigit():
                used_indexes.add(int(suffix))
        next_index = 1
        while next_index in used_indexes:
            next_index += 1
        return f"{prefix}{next_index:04d}"

    def _entry_description(self, entry):
        category = (
            entry.class_beginner if entry.is_beginner else
            entry.class_20 if entry.is_20 else
            entry.class_24 if entry.is_24 else
            ""
        )
        return f"{entry.rider.first_name} {entry.rider.last_name}, UCI ID {entry.rider.uci_id}, {category}"

    def _collect_club_lines(self, event):
        entries = (
            Entry.objects.filter(
                event=event,
                payment_complete=True,
                checkout=False,
                rider__club__isnull=False,
            )
            .select_related("rider", "rider__club")
            .order_by("rider__club__team_name", "rider__last_name", "rider__first_name")
        )

        by_club = defaultdict(list)
        for entry in entries:
            club = entry.rider.club
            if not club:
                continue
            rider_label = self._entry_description(entry)
            if entry.is_beginner and entry.fee_beginner:
                by_club[club].append(
                    InvoiceLine(
                        description=rider_label,
                        quantity=1,
                        unit_price=_money(entry.fee_beginner),
                    )
                )
            if entry.is_20 and entry.fee_20:
                by_club[club].append(
                    InvoiceLine(
                        description=rider_label,
                        quantity=1,
                        unit_price=_money(entry.fee_20),
                    )
                )
            if entry.is_24 and entry.fee_24:
                by_club[club].append(
                    InvoiceLine(
                        description=rider_label,
                        quantity=1,
                        unit_price=_money(entry.fee_24),
                    )
                )
        return dict(by_club)

    def _apply_manual_overrides(self, event, club_lines):
        overrides = {
            override.club_id: override
            for override in EventInvoiceOverride.objects.filter(event=event)
        }
        for club, lines in club_lines.items():
            override = overrides.get(club.id)
            if not override or not override.manual_descriptions.strip():
                continue
            manual_lines = [line.strip() for line in override.manual_descriptions.splitlines() if line.strip()]
            manual_amounts = [line.strip() for line in (override.manual_amounts or "").splitlines() if line.strip()]
            if not manual_lines or len(manual_lines) != len(manual_amounts):
                continue
            overridden_lines = []
            for index, manual_description in enumerate(manual_lines):
                try:
                    unit_price = _money(Decimal(manual_amounts[index].replace(",", ".")))
                except (InvalidOperation, ValueError):
                    continue
                overridden_lines.append(
                    InvoiceLine(
                        description=manual_description,
                        quantity=1,
                        unit_price=unit_price,
                    )
                )
            if overridden_lines:
                club_lines[club] = overridden_lines
        return club_lines

    def get_club_lines(self, event):
        return self._apply_manual_overrides(event, self._collect_club_lines(event))

    def get_club_previews(self, event):
        previews = []
        for club, lines in sorted(self.get_club_lines(event).items(), key=lambda item: item[0].team_name):
            previews.append({
                "club": club,
                "lines": lines,
                "manual_descriptions": "\n".join(line.description for line in lines),
                "manual_amounts": "\n".join(f"{line.unit_price:.2f}" for line in lines),
                "total": _money(sum(line.total for line in lines)),
            })
        return previews

    def _rebuild_event_export(self, event):
        invoices = EventInvoice.objects.filter(event=event).select_related("club").order_by("club__team_name")
        if not invoices.exists():
            if event.flexibee_export:
                event.flexibee_export.delete(save=False)
                event.flexibee_export = ""
                event.save(update_fields=["flexibee_export"])
            return

        club_lines = self.get_club_lines(event)
        payload = []
        for invoice in invoices:
            payload.append({"invoice": invoice, "lines": club_lines.get(invoice.club, [])})
        xml_bytes = self._build_flexibee_xml(payload)
        event.flexibee_export.save(
            f"event-{event.id}-invoices.xml",
            ContentFile(xml_bytes),
            save=True,
        )

    def _invoice_filename_base(self, invoice):
        event_slug = slugify(invoice.event.name) or f"event-{invoice.event_id}"
        club_slug = slugify(invoice.club.team_name) or f"club-{invoice.club_id}"
        return f"{invoice.number}-{event_slug}-{club_slug}"

    def _supplier_lines(self, event):
        lines = [
            SUPPLIER_NAME,
            SUPPLIER_STREET,
            SUPPLIER_CITY,
            SUPPLIER_COUNTRY,
            f"IČ: {SUPPLIER_ICO}",
            "Nejsme plátci DPH",
        ]
        organizer = event.organizer
        if organizer and organizer.bank_account:
            lines.append(f"Bankovní účet: {organizer.bank_account}")
        return lines

    def _customer_lines(self, club):
        address = ", ".join(filter(None, [club.street, f"{club.zip_code} {club.city}".strip()]))
        lines = [club.team_name]
        if address.strip(", "):
            lines.append(address)
        if club.ico:
            lines.append(f"IČ: {club.ico}")
        if club.billing_email:
            lines.append(f"E-mail: {club.billing_email}")
        elif club.contact_email:
            lines.append(f"E-mail: {club.contact_email}")
        return lines

    def _draw_invoice_page_header(self, pdf, invoice, include_parties=True):
        width, height = A4
        seal_x = 20 * mm
        seal_y = height - 30 * mm
        seal_size = 18 * mm
        header_x = 20 * mm
        header_y = seal_y - 8 * mm

        if os.path.exists(ISDOC_SEAL_PATH):
            pdf.drawImage(
                ISDOC_SEAL_PATH,
                seal_x,
                seal_y,
                width=seal_size,
                height=seal_size,
                preserveAspectRatio=True,
                mask="auto",
            )
        else:
            pdf.setFillColor(colors.HexColor("#E6FFFA"))
            pdf.setStrokeColor(colors.HexColor("#0F766E"))
            pdf.roundRect(seal_x, seal_y, seal_size, seal_size, 4 * mm, fill=1, stroke=1)
            pdf.setFillColor(colors.HexColor("#0F766E"))
            pdf.setFont("DejaVuSans-Bold", 8)
            pdf.drawCentredString(seal_x + seal_size / 2, seal_y + 11.5 * mm, "ISDOC")
            pdf.setFont("DejaVuSans", 5.5)
            pdf.drawCentredString(seal_x + seal_size / 2, seal_y + 7.2 * mm, "vlozeno v PDF")
            pdf.setFont("DejaVuSans-Bold", 5.5)
            pdf.drawCentredString(seal_x + seal_size / 2, seal_y + 3.4 * mm, "HYBRID")

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

        pdf.setFillColor(colors.black)
        pdf.setTitle(f"Faktura {invoice.number}")
        pdf.setFont("DejaVuSans-Bold", 18)
        pdf.drawString(header_x, header_y, f"Faktura č. {invoice.number}")

        pdf.setFont("DejaVuSans", 10)
        pdf.drawString(header_x, header_y - 12 * mm, f"Datum vystavení: {invoice.issue_date:%d.%m.%Y}")
        pdf.drawString(header_x, header_y - 18 * mm, f"Datum splatnosti: {invoice.due_date:%d.%m.%Y}")
        pdf.drawString(header_x, header_y - 24 * mm, f"Variabilní symbol: {invoice.number}")

        if not include_parties:
            return header_y - 34 * mm

        pdf.setFont("DejaVuSans-Bold", 11)
        pdf.drawString(20 * mm, header_y - 44 * mm, "Dodavatel")
        pdf.drawString(110 * mm, header_y - 44 * mm, "Odběratel")

        pdf.setFont("DejaVuSans", 10)
        supplier_y = header_y - 52 * mm
        for line in self._supplier_lines(invoice.event):
            pdf.drawString(20 * mm, supplier_y, line)
            supplier_y -= 5 * mm

        customer_y = header_y - 52 * mm
        for line in self._customer_lines(invoice.club):
            pdf.drawString(110 * mm, customer_y, line)
            customer_y -= 5 * mm

        subject_y = min(supplier_y, customer_y) - 8 * mm
        pdf.setFont("DejaVuSans-Bold", 10)
        pdf.drawString(20 * mm, subject_y, "Předmět: ")
        pdf.setFont("DejaVuSans", 10)
        if invoice.event.date:
            subject_text = f"fakturujeme Vám startovné za závod {invoice.event.name} konaný dne {invoice.event.date:%d.%m.%Y}"
        else:
            subject_text = f"fakturujeme Vám startovné za závod {invoice.event.name}"

        subject_lines = simpleSplit(subject_text, "DejaVuSans", 10, 148 * mm)
        for index, line in enumerate(subject_lines):
            pdf.drawString(41 * mm, subject_y - (index * 5 * mm), line)
        return subject_y - ((len(subject_lines) - 1) * 5 * mm)

    def _draw_invoice_table_header(self, pdf, table_top):
        pdf.setFillColor(colors.HexColor("#1E293B"))
        pdf.rect(20 * mm, table_top, 170 * mm, 8 * mm, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setFont("DejaVuSans-Bold", 9)
        pdf.drawString(24 * mm, table_top + 2.5 * mm, "Položka")
        pdf.drawRightString(187 * mm, table_top + 2.5 * mm, "Cena")

    def _draw_invoice_summary(self, pdf, invoice, current_y):
        pdf.setFillColor(colors.black)
        current_y -= 6 * mm
        pdf.setFont("DejaVuSans-Bold", 10)
        pdf.drawString(20 * mm, current_y, "NEPLAŤTE, UHRAZENO PLATEBNÍ BRÁNOU")
        current_y -= 4 * mm
        pdf.line(120 * mm, current_y, 190 * mm, current_y)
        current_y -= 7 * mm
        pdf.setFont("DejaVuSans-Bold", 11)
        pdf.drawRightString(152 * mm, current_y, "Celková částka")
        pdf.drawRightString(187 * mm, current_y, f"{invoice.total_price:.2f} Kč")
        current_y -= 7 * mm
        pdf.drawRightString(152 * mm, current_y, "K úhradě")
        pdf.drawRightString(187 * mm, current_y, "0.00 Kč")
        current_y -= 12 * mm
        pdf.setFont("DejaVuSans", 9)
        pdf.drawString(20 * mm, current_y, "Faktura byla vygenerována automaticky z uhrazených registrací závodu.")

    def _generate_pdf(self, invoice, lines):
        buffer = BytesIO()
        pdf = NumberedCanvas(buffer, pagesize=A4)
        _, height = A4
        generated_at = timezone.localtime().strftime("%d.%m.%Y %H:%M")
        footer_left = f"Startovné | {invoice.event.name}"
        footer_right = f"Generováno {generated_at}"

        subject_bottom_y = self._draw_invoice_page_header(pdf, invoice, include_parties=True)
        table_top = subject_bottom_y - 16 * mm
        self._draw_invoice_table_header(pdf, table_top)

        current_y = table_top - 7 * mm
        bottom_limit = 30 * mm
        summary_reserved = 42 * mm

        for line in lines:
            description_lines = simpleSplit(line.description, "DejaVuSans", 9, 116 * mm) or [line.description]
            row_height = max(6 * mm, (len(description_lines) * 4.6 * mm) + 1.5 * mm)

            if current_y - row_height < bottom_limit + summary_reserved:
                draw_pdf_footer(pdf, left_text=footer_left, right_text=footer_right)
                pdf.showPage()
                header_bottom_y = self._draw_invoice_page_header(pdf, invoice, include_parties=False)
                table_top = header_bottom_y - 10 * mm
                self._draw_invoice_table_header(pdf, table_top)
                current_y = table_top - 7 * mm

            pdf.setFillColor(colors.black)
            pdf.setFont("DejaVuSans", 9)
            text_y = current_y
            for description_line in description_lines:
                pdf.drawString(24 * mm, text_y, description_line)
                text_y -= 4.6 * mm
            pdf.drawRightString(187 * mm, current_y, f"{line.unit_price:.2f} Kč")
            current_y -= row_height

        if current_y - summary_reserved < bottom_limit:
            draw_pdf_footer(pdf, left_text=footer_left, right_text=footer_right)
            pdf.showPage()
            header_bottom_y = self._draw_invoice_page_header(pdf, invoice, include_parties=False)
            table_top = header_bottom_y - 10 * mm
            self._draw_invoice_table_header(pdf, table_top)
            current_y = table_top - 7 * mm

        self._draw_invoice_summary(pdf, invoice, current_y)
        draw_pdf_footer(pdf, left_text=footer_left, right_text=footer_right)
        pdf.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _isdoc_tag(self, name):
        return f"{{{ISDOC_NS}}}{name}"

    def _append_isdoc_text(self, parent, name, value):
        node = ET.SubElement(parent, self._isdoc_tag(name))
        node.text = value
        return node

    def _build_isdoc_xml(self, invoice, lines):
        total = _money(sum(line.total for line in lines))
        root = ET.Element(
            self._isdoc_tag("Invoice"),
            {
                "version": "6.0.2",
                f"{{{SCHEMA_INSTANCE_NS}}}schemaLocation": (
                    "http://isdoc.cz/namespace/2013 "
                    "http://isdoc.cz/6.0.2/xsd/isdoc-invoice-6.0.2.xsd"
                ),
            },
        )
        self._append_isdoc_text(root, "DocumentType", "1")
        self._append_isdoc_text(root, "ID", invoice.number)
        self._append_isdoc_text(
            root,
            "UUID",
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{invoice.event_id}:{invoice.club_id}:{invoice.number}")),
        )
        self._append_isdoc_text(root, "IssueDate", invoice.issue_date.isoformat())
        self._append_isdoc_text(root, "TaxPointDate", invoice.issue_date.isoformat())
        self._append_isdoc_text(root, "VATApplicable", "false")
        self._append_isdoc_text(root, "ElectronicPossibilityAgreementReference", "false")
        self._append_isdoc_text(root, "Note", "NEPLAŤTE, UHRAZENO PLATEBNÍ BRÁNOU")
        self._append_isdoc_text(root, "LocalCurrencyCode", "CZK")
        self._append_isdoc_text(root, "CurrRate", "1")

        supplier_party = ET.SubElement(root, self._isdoc_tag("AccountingSupplierParty"))
        supplier_identification = ET.SubElement(supplier_party, self._isdoc_tag("PartyIdentification"))
        self._append_isdoc_text(supplier_identification, "ID", SUPPLIER_ICO)
        supplier_name = ET.SubElement(supplier_party, self._isdoc_tag("PartyName"))
        self._append_isdoc_text(supplier_name, "Name", SUPPLIER_NAME)
        supplier_address = ET.SubElement(supplier_party, self._isdoc_tag("PostalAddress"))
        self._append_isdoc_text(supplier_address, "StreetName", SUPPLIER_STREET)
        self._append_isdoc_text(supplier_address, "CityName", "Praha 3")
        self._append_isdoc_text(supplier_address, "PostalZone", "130 00")
        supplier_country = ET.SubElement(supplier_address, self._isdoc_tag("Country"))
        self._append_isdoc_text(supplier_country, "IdentificationCode", "CZ")
        supplier_tax_scheme = ET.SubElement(supplier_party, self._isdoc_tag("PartyTaxScheme"))
        self._append_isdoc_text(supplier_tax_scheme, "CompanyID", SUPPLIER_ICO)

        customer_party = ET.SubElement(root, self._isdoc_tag("AccountingCustomerParty"))
        customer_name = ET.SubElement(customer_party, self._isdoc_tag("PartyName"))
        self._append_isdoc_text(customer_name, "Name", invoice.club.team_name)
        if invoice.club.ico:
            customer_identification = ET.SubElement(customer_party, self._isdoc_tag("PartyIdentification"))
            self._append_isdoc_text(customer_identification, "ID", invoice.club.ico)
            customer_tax_scheme = ET.SubElement(customer_party, self._isdoc_tag("PartyTaxScheme"))
            self._append_isdoc_text(customer_tax_scheme, "CompanyID", invoice.club.ico)
        if invoice.club.street or invoice.club.city or invoice.club.zip_code:
            customer_address = ET.SubElement(customer_party, self._isdoc_tag("PostalAddress"))
            if invoice.club.street:
                self._append_isdoc_text(customer_address, "StreetName", invoice.club.street)
            if invoice.club.city:
                self._append_isdoc_text(customer_address, "CityName", invoice.club.city)
            if invoice.club.zip_code:
                self._append_isdoc_text(customer_address, "PostalZone", invoice.club.zip_code)
            customer_country = ET.SubElement(customer_address, self._isdoc_tag("Country"))
            self._append_isdoc_text(customer_country, "IdentificationCode", "CZ")

        invoice_lines = ET.SubElement(root, self._isdoc_tag("InvoiceLines"))
        for index, line in enumerate(lines, start=1):
            item = ET.SubElement(invoice_lines, self._isdoc_tag("InvoiceLine"))
            self._append_isdoc_text(item, "ID", str(index))
            self._append_isdoc_text(item, "InvoicedQuantity", str(line.quantity))
            self._append_isdoc_text(item, "LineExtensionAmount", f"{line.total:.2f}")
            self._append_isdoc_text(item, "LineExtensionAmountTaxInclusive", f"{line.total:.2f}")
            self._append_isdoc_text(item, "LineExtensionTaxAmount", "0.00")
            self._append_isdoc_text(item, "UnitPrice", f"{line.unit_price:.2f}")
            item_detail = ET.SubElement(item, self._isdoc_tag("Item"))
            self._append_isdoc_text(item_detail, "Description", line.description)
            tax_total = ET.SubElement(item, self._isdoc_tag("TaxTotal"))
            self._append_isdoc_text(tax_total, "TaxAmount", "0.00")

        tax_total = ET.SubElement(root, self._isdoc_tag("TaxTotal"))
        self._append_isdoc_text(tax_total, "TaxAmount", "0.00")

        monetary_total = ET.SubElement(root, self._isdoc_tag("LegalMonetaryTotal"))
        self._append_isdoc_text(monetary_total, "TaxExclusiveAmount", f"{total:.2f}")
        self._append_isdoc_text(monetary_total, "TaxInclusiveAmount", f"{total:.2f}")
        self._append_isdoc_text(monetary_total, "AlreadyClaimedTaxExclusiveAmount", f"{total:.2f}")
        self._append_isdoc_text(monetary_total, "AlreadyClaimedTaxInclusiveAmount", f"{total:.2f}")
        self._append_isdoc_text(monetary_total, "PayableAmount", "0.00")

        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _embed_isdoc_into_pdf(self, pdf_bytes, isdoc_bytes):
        if pikepdf is None:
            return pdf_bytes

        pdf = pikepdf.Pdf.open(BytesIO(pdf_bytes))
        attachment = pikepdf.AttachedFileSpec(
            pdf,
            isdoc_bytes,
            filename="invoice.isdoc",
            mime_type="application/x-isdoc+xml",
            relationship=pikepdf.Name("/Alternative"),
            description="ISDOC 6.0.2 invoice attachment",
        )
        pdf.attachments["invoice.isdoc"] = attachment
        pdf.Root.AF = pikepdf.Array([attachment.obj])

        output = BytesIO()
        pdf.save(output)
        return output.getvalue()

    def _build_flexibee_xml(self, invoices_payload):
        root = ET.Element("winstrom", version="1.0")
        for payload in invoices_payload:
            invoice = payload["invoice"]
            lines = payload["lines"]
            doc = ET.SubElement(root, "faktura-vydana", action="create")
            ET.SubElement(doc, "kod").text = invoice.number
            ET.SubElement(doc, "typDokl").text = "code:FAKTURA"
            ET.SubElement(doc, "varSym").text = invoice.number
            ET.SubElement(doc, "datVyst").text = invoice.issue_date.isoformat()
            ET.SubElement(doc, "datSplat").text = invoice.due_date.isoformat()
            ET.SubElement(doc, "sumCelkem").text = f"{invoice.total_price:.2f}"
            ET.SubElement(doc, "mena").text = "code:CZK"
            ET.SubElement(doc, "nazFirmy").text = invoice.club.team_name
            if invoice.club.ico:
                ET.SubElement(doc, "ic").text = invoice.club.ico
            if invoice.club.street:
                ET.SubElement(doc, "ulice").text = invoice.club.street
            if invoice.club.city:
                ET.SubElement(doc, "mesto").text = invoice.club.city
            if invoice.club.zip_code:
                ET.SubElement(doc, "psc").text = invoice.club.zip_code
            billing_email = invoice.club.billing_email or invoice.club.contact_email
            if billing_email:
                ET.SubElement(doc, "email").text = billing_email
            event_label = f"{invoice.event.date:%d.%m.%Y} - {invoice.event.name}" if invoice.event.date else invoice.event.name
            ET.SubElement(doc, "popis").text = f"Startovné za závod {event_label}"

            items_node = ET.SubElement(doc, "polozkyFaktury")
            for line in lines:
                item = ET.SubElement(items_node, "faktura-vydana-polozka", action="create")
                ET.SubElement(item, "nazev").text = line.description
                ET.SubElement(item, "mnozMj").text = str(line.quantity)
                ET.SubElement(item, "cenaMj").text = f"{line.unit_price:.2f}"
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _save_invoice_files(self, invoice, lines):
        file_base = self._invoice_filename_base(invoice)
        pdf_bytes = self._generate_pdf(invoice, lines)
        isdoc_bytes = self._build_isdoc_xml(invoice, lines)
        pdf_bytes = self._embed_isdoc_into_pdf(pdf_bytes, isdoc_bytes)
        xml_bytes = self._build_flexibee_xml([{"invoice": invoice, "lines": lines}])

        invoice.pdf.save(f"{file_base}.pdf", ContentFile(pdf_bytes), save=False)
        invoice.xml_export.save(f"{file_base}.xml", ContentFile(xml_bytes), save=False)

    def _send_invoice_email(self, invoice):
        recipient = invoice.club.billing_email or invoice.club.contact_email
        if not recipient or not invoice.pdf:
            return False, recipient

        message = EmailMessage(
            subject=f"Faktura za zavod {invoice.event.name} - {invoice.number}",
            body=(
                f"Dobrý den,\n\n"
                f"v příloze zasíláme fakturu {invoice.number} za závod {invoice.event.name}.\n"
                f"Částka byla uhrazena platební bránou, fakturu proto neplaťte.\n\n"
                f"Czech BMX"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        invoice.pdf.open("rb")
        try:
            message.attach(os.path.basename(invoice.pdf.name), invoice.pdf.read(), "application/pdf")
        finally:
            invoice.pdf.close()
        message.send(fail_silently=False)
        invoice.email_sent_at = timezone.now()
        invoice.email_sent_to = recipient
        return True, recipient

    def delete_invoice(self, invoice):
        event = invoice.event
        if invoice.pdf:
            invoice.pdf.delete(save=False)
        if invoice.xml_export:
            invoice.xml_export.delete(save=False)
        invoice.delete()
        self._rebuild_event_export(event)

    @transaction.atomic
    def generate_for_event(self, event):
        club_lines = self.get_club_lines(event)
        generated = []
        current_club_ids = {club.id for club in club_lines.keys()}

        stale_invoices = EventInvoice.objects.filter(event=event).exclude(club_id__in=current_club_ids)
        for stale_invoice in stale_invoices:
            self.delete_invoice(stale_invoice)

        for club, lines in club_lines.items():
            total = _money(sum(line.total for line in lines))
            if total <= 0:
                continue

            issue_date = timezone.localdate()
            due_date = issue_date
            invoice, created = EventInvoice.objects.get_or_create(
                event=event,
                club=club,
                defaults={
                    "number": self._build_invoice_number(),
                    "issue_date": issue_date,
                    "due_date": due_date,
                    "total_price": total,
                },
            )
            invoice.issue_date = issue_date
            invoice.due_date = due_date
            invoice.total_price = total
            if created and not invoice.number:
                invoice.number = self._build_invoice_number()
            self._save_invoice_files(invoice, lines)
            invoice.save()
            generated.append(invoice)

        self._rebuild_event_export(event)

        return {
            "generated": generated,
            "sent": [],
            "skipped": [],
            "xml_path": event.flexibee_export.name if event.flexibee_export else "",
        }

    @transaction.atomic
    def send_for_event(self, event):
        invoices = list(EventInvoice.objects.filter(event=event).select_related("club").order_by("club__team_name"))
        sent = []
        skipped = []
        for invoice in invoices:
            delivered, recipient = self._send_invoice_email(invoice)
            invoice.save(update_fields=["email_sent_at", "email_sent_to", "updated"])
            if delivered:
                sent.append((invoice, recipient))
            else:
                skipped.append((invoice, recipient))
        return {
            "generated": invoices,
            "sent": sent,
            "skipped": skipped,
            "xml_path": event.flexibee_export.name if event.flexibee_export else "",
        }

    @transaction.atomic
    def update_invoice_for_club(self, event, club):
        lines = self.get_club_lines(event).get(club, [])
        invoice = EventInvoice.objects.filter(event=event, club=club).first()
        if not lines:
            if invoice:
                self.delete_invoice(invoice)
            self._rebuild_event_export(event)
            return None
        if not invoice:
            return None
        invoice.issue_date = timezone.localdate()
        invoice.due_date = invoice.issue_date
        invoice.total_price = _money(sum(line.total for line in lines))
        self._save_invoice_files(invoice, lines)
        invoice.save()
        self._rebuild_event_export(event)
        return invoice


def generate_event_invoices(event_id):
    event = Event.objects.select_related("organizer").get(pk=event_id)
    return EventInvoiceService().generate_for_event(event)


def send_event_invoices(event_id):
    event = Event.objects.select_related("organizer").get(pk=event_id)
    return EventInvoiceService().send_for_event(event)


def save_invoice_override(event, club, manual_descriptions, manual_amounts):
    override, _ = EventInvoiceOverride.objects.get_or_create(event=event, club=club)
    override.manual_descriptions = manual_descriptions.strip()
    override.manual_amounts = manual_amounts.strip()
    override.save(update_fields=["manual_descriptions", "manual_amounts", "updated"])
    EventInvoiceService().update_invoice_for_club(event, club)
    return override


def delete_invoice_override(event, club):
    EventInvoiceOverride.objects.filter(event=event, club=club).delete()
    return EventInvoiceService().update_invoice_for_club(event, club)
