from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
import xml.etree.ElementTree as ET

from django.core.files.base import ContentFile
from django.db import transaction
from django.template.defaultfilters import slugify
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit

from finance.invoices import (
    COST_CENTER_CODE,
    ISDOC_NS,
    LOGO_PATH,
    NumberedCanvas,
    SCHEMA_INSTANCE_NS,
    SUPPLIER_CITY,
    SUPPLIER_COUNTRY,
    SUPPLIER_ICO,
    SUPPLIER_NAME,
    SUPPLIER_STREET,
    draw_pdf_footer,
    _money,
    _register_fonts,
)
from finance.models import SubscriptionInvoice
from rider.models import MobileAppCharge, RiderStatsCharge, TrainerClubCharge, TrainerClubSubscription


ET.register_namespace("", ISDOC_NS)
ET.register_namespace("xsi", SCHEMA_INSTANCE_NS)


@dataclass
class SubscriptionInvoiceLine:
    description: str
    quantity: int
    unit_price: Decimal

    @property
    def total(self):
        return _money(self.quantity * self.unit_price)


class SubscriptionInvoiceService:
    def __init__(self):
        _register_fonts()

    def _build_invoice_number(self):
        year = timezone.localdate().year
        prefix = f"{COST_CENTER_CODE}SUB{year}"
        used_indexes = set()
        for number in SubscriptionInvoice.objects.filter(number__startswith=prefix).values_list("number", flat=True):
            suffix = str(number)[len(prefix):]
            if suffix.isdigit():
                used_indexes.add(int(suffix))
        next_index = 1
        while next_index in used_indexes:
            next_index += 1
        return f"{prefix}{next_index:04d}"

    def _customer_lines(self, invoice):
        lines = [invoice.customer_name]
        if invoice.customer_email:
            lines.append(f"E-mail: {invoice.customer_email}")
        return lines

    def _supplier_lines(self):
        return [
            SUPPLIER_NAME,
            SUPPLIER_STREET,
            SUPPLIER_CITY,
            SUPPLIER_COUNTRY,
            f"IČ: {SUPPLIER_ICO}",
            "Nejsme plátci DPH",
        ]

    def _invoice_filename_base(self, invoice):
        customer_slug = slugify(invoice.customer_name) or f"user-{invoice.user_id}"
        return f"{invoice.number}-{customer_slug}"

    def _line_for_invoice(self, invoice):
        return SubscriptionInvoiceLine(
            description=invoice.description,
            quantity=1,
            unit_price=_money(invoice.total_price),
        )

    def _draw_invoice_header(self, pdf, invoice):
        width, height = A4
        pdf.setTitle(f"Faktura {invoice.number}")
        if LOGO_PATH:
            try:
                pdf.drawImage(
                    LOGO_PATH,
                    width - 48 * mm,
                    height - 28 * mm,
                    width=28 * mm,
                    height=18 * mm,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass

        top_y = height - 24 * mm
        pdf.setFont("DejaVuSans-Bold", 18)
        pdf.drawString(20 * mm, top_y, f"Faktura č. {invoice.number}")

        pdf.setFont("DejaVuSans", 10)
        pdf.drawString(20 * mm, top_y - 12 * mm, f"Datum vystavení: {invoice.issue_date:%d.%m.%Y}")
        pdf.drawString(20 * mm, top_y - 18 * mm, f"Datum splatnosti: {invoice.due_date:%d.%m.%Y}")
        pdf.drawString(20 * mm, top_y - 24 * mm, f"Variabilní symbol: {invoice.number}")

        pdf.setFont("DejaVuSans-Bold", 11)
        pdf.drawString(20 * mm, top_y - 40 * mm, "Dodavatel")
        pdf.drawString(110 * mm, top_y - 40 * mm, "Odběratel")

        pdf.setFont("DejaVuSans", 10)
        supplier_y = top_y - 48 * mm
        for line in self._supplier_lines():
            pdf.drawString(20 * mm, supplier_y, line)
            supplier_y -= 5 * mm

        customer_y = top_y - 48 * mm
        for line in self._customer_lines(invoice):
            pdf.drawString(110 * mm, customer_y, line)
            customer_y -= 5 * mm

        note_y = min(supplier_y, customer_y) - 8 * mm
        pdf.setFont("DejaVuSans-Bold", 10)
        pdf.drawString(20 * mm, note_y, "Předmět:")
        pdf.setFont("DejaVuSans", 10)
        for idx, line in enumerate(simpleSplit(invoice.description, "DejaVuSans", 10, 148 * mm)):
            pdf.drawString(40 * mm, note_y - (idx * 5 * mm), line)
        return note_y - 12 * mm

    def _draw_table_header(self, pdf, top_y):
        pdf.setFillColor(colors.HexColor("#1E293B"))
        pdf.rect(20 * mm, top_y, 170 * mm, 8 * mm, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setFont("DejaVuSans-Bold", 9)
        pdf.drawString(24 * mm, top_y + 2.5 * mm, "Položka")
        pdf.drawString(145 * mm, top_y + 2.5 * mm, "Cena")
        pdf.drawString(172 * mm, top_y + 2.5 * mm, "Celkem")

    def _generate_pdf(self, invoice):
        buffer = BytesIO()
        pdf = NumberedCanvas(buffer, pagesize=A4)
        generated_at = timezone.localtime().strftime("%d.%m.%Y %H:%M")
        line = self._line_for_invoice(invoice)
        current_y = self._draw_invoice_header(pdf, invoice)
        table_top = current_y - 8 * mm
        self._draw_table_header(pdf, table_top)

        row_y = table_top - 7 * mm
        pdf.setFillColor(colors.black)
        pdf.setFont("DejaVuSans", 9)
        for idx, text_line in enumerate(simpleSplit(line.description, "DejaVuSans", 9, 116 * mm)):
            pdf.drawString(24 * mm, row_y - (idx * 4.6 * mm), text_line)
        pdf.drawRightString(164 * mm, row_y, f"{line.unit_price:.2f} Kč")
        pdf.drawRightString(187 * mm, row_y, f"{line.total:.2f} Kč")

        summary_y = row_y - 22 * mm
        pdf.setFont("DejaVuSans-Bold", 10)
        pdf.drawString(20 * mm, summary_y, "UHRAZENO Z KREDITU UŽIVATELE")
        pdf.line(120 * mm, summary_y - 3 * mm, 190 * mm, summary_y - 3 * mm)
        pdf.setFont("DejaVuSans-Bold", 11)
        pdf.drawString(129 * mm, summary_y - 12 * mm, "Celková částka")
        pdf.drawRightString(187 * mm, summary_y - 12 * mm, f"{invoice.total_price:.2f} Kč")
        pdf.setFont("DejaVuSans", 9)
        pdf.drawString(20 * mm, summary_y - 24 * mm, "Faktura byla vytvořena automaticky po stržení kreditu za předplatné.")
        draw_pdf_footer(
            pdf,
            left_text=f"Předplatné | {invoice.get_invoice_type_display()}",
            right_text=f"Generováno {generated_at}",
        )
        pdf.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _build_flexibee_xml(self, invoice):
        root = ET.Element("winstrom", version="1.0")
        doc = ET.SubElement(root, "faktura-vydana", action="create")
        ET.SubElement(doc, "kod").text = invoice.number
        ET.SubElement(doc, "typDokl").text = "code:FAKTURA"
        ET.SubElement(doc, "varSym").text = invoice.number
        ET.SubElement(doc, "datVyst").text = invoice.issue_date.isoformat()
        ET.SubElement(doc, "datSplat").text = invoice.due_date.isoformat()
        ET.SubElement(doc, "sumCelkem").text = f"{invoice.total_price:.2f}"
        ET.SubElement(doc, "mena").text = "code:CZK"
        ET.SubElement(doc, "nazFirmy").text = invoice.customer_name
        if invoice.customer_email:
            ET.SubElement(doc, "email").text = invoice.customer_email
        ET.SubElement(doc, "popis").text = invoice.description

        items = ET.SubElement(doc, "polozkyFaktury")
        item = ET.SubElement(items, "faktura-vydana-polozka", action="create")
        ET.SubElement(item, "nazev").text = invoice.description
        ET.SubElement(item, "mnozMj").text = "1"
        ET.SubElement(item, "cenaMj").text = f"{invoice.total_price:.2f}"
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _save_invoice_files(self, invoice):
        file_base = self._invoice_filename_base(invoice)
        pdf_bytes = self._generate_pdf(invoice)
        xml_bytes = self._build_flexibee_xml(invoice)
        invoice.pdf.save(f"{file_base}.pdf", ContentFile(pdf_bytes), save=False)
        invoice.xml_export.save(f"{file_base}.xml", ContentFile(xml_bytes), save=False)

    def _build_rider_description(self, charge):
        return f"Měsíční předplatné prémiových statistik jezdce {charge.rider.first_name} {charge.rider.last_name} za období {timezone.localtime(charge.period_start):%d.%m.%Y} – {timezone.localtime(charge.period_end):%d.%m.%Y}"

    def _build_trainer_description(self, charge):
        if charge.product == TrainerClubSubscription.PRODUCT_CLUB_STATS:
            return f"Měsíční klubové předplatné trenéra pro klub {charge.club.team_name} za období {timezone.localtime(charge.period_start):%d.%m.%Y} – {timezone.localtime(charge.period_end):%d.%m.%Y}"
        return f"Měsíční rozšířené trenérské předplatné za období {timezone.localtime(charge.period_start):%d.%m.%Y} – {timezone.localtime(charge.period_end):%d.%m.%Y}"

    def _build_mobile_description(self, charge):
        return f"Měsíční předplatné mobilní aplikace za období {timezone.localtime(charge.period_start):%d.%m.%Y} – {timezone.localtime(charge.period_end):%d.%m.%Y}"

    @transaction.atomic
    def generate_for_rider_charge(self, charge):
        if not charge.payment_valid:
            return None
        existing = SubscriptionInvoice.objects.filter(rider_charge=charge).first()
        if existing:
            return existing
        invoice = SubscriptionInvoice.objects.create(
            number=self._build_invoice_number(),
            issue_date=timezone.localdate(charge.transaction_date),
            due_date=timezone.localdate(charge.transaction_date),
            user=charge.user,
            invoice_type=SubscriptionInvoice.TYPE_RIDER_STATS,
            description=self._build_rider_description(charge),
            customer_name=f"{charge.user.first_name} {charge.user.last_name}".strip() or charge.user.username,
            customer_email=charge.user.email or "",
            total_price=_money(charge.amount),
            rider_charge=charge,
        )
        self._save_invoice_files(invoice)
        invoice.save()
        return invoice

    @transaction.atomic
    def generate_for_trainer_charge(self, charge):
        if not charge.payment_valid:
            return None
        existing = SubscriptionInvoice.objects.filter(trainer_charge=charge).first()
        if existing:
            return existing
        invoice_type = (
            SubscriptionInvoice.TYPE_TRAINER_CLUB
            if charge.product == TrainerClubSubscription.PRODUCT_CLUB_STATS
            else SubscriptionInvoice.TYPE_TRAINER_EXTENDED
        )
        if charge.product == TrainerClubSubscription.PRODUCT_CLUB_STATS:
            customer_name = charge.club.team_name
            customer_email = charge.club.billing_email or charge.club.contact_email or ""
        else:
            customer_name = f"{charge.user.first_name} {charge.user.last_name}".strip() or charge.user.username
            customer_email = charge.user.email or ""
        invoice = SubscriptionInvoice.objects.create(
            number=self._build_invoice_number(),
            issue_date=timezone.localdate(charge.transaction_date),
            due_date=timezone.localdate(charge.transaction_date),
            user=charge.user,
            invoice_type=invoice_type,
            description=self._build_trainer_description(charge),
            customer_name=customer_name,
            customer_email=customer_email,
            total_price=_money(charge.amount),
            trainer_charge=charge,
        )
        self._save_invoice_files(invoice)
        invoice.save()
        return invoice

    @transaction.atomic
    def generate_for_mobile_charge(self, charge):
        if not charge.payment_valid:
            return None
        existing = SubscriptionInvoice.objects.filter(mobile_charge=charge).first()
        if existing:
            return existing
        invoice = SubscriptionInvoice.objects.create(
            number=self._build_invoice_number(),
            issue_date=timezone.localdate(charge.transaction_date),
            due_date=timezone.localdate(charge.transaction_date),
            user=charge.user,
            invoice_type=SubscriptionInvoice.TYPE_MOBILE_APP,
            description=self._build_mobile_description(charge),
            customer_name=f"{charge.user.first_name} {charge.user.last_name}".strip() or charge.user.username,
            customer_email=charge.user.email or "",
            total_price=_money(charge.amount),
            mobile_charge=charge,
        )
        self._save_invoice_files(invoice)
        invoice.save()
        return invoice

    def ensure_for_user(self, user):
        for charge in RiderStatsCharge.objects.filter(user=user, payment_valid=True, invoice__isnull=True).select_related("rider", "user"):
            self.generate_for_rider_charge(charge)
        for charge in TrainerClubCharge.objects.filter(user=user, payment_valid=True, invoice__isnull=True).select_related("club", "user"):
            self.generate_for_trainer_charge(charge)
        for charge in MobileAppCharge.objects.filter(user=user, payment_valid=True, invoice__isnull=True).select_related("user"):
            self.generate_for_mobile_charge(charge)

    def ensure_for_all(self):
        for charge in RiderStatsCharge.objects.filter(payment_valid=True, invoice__isnull=True).select_related("rider", "user"):
            self.generate_for_rider_charge(charge)
        for charge in TrainerClubCharge.objects.filter(payment_valid=True, invoice__isnull=True).select_related("club", "user"):
            self.generate_for_trainer_charge(charge)
        for charge in MobileAppCharge.objects.filter(payment_valid=True, invoice__isnull=True).select_related("user"):
            self.generate_for_mobile_charge(charge)
