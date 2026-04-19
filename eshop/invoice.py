"""PDF invoice generator for eshop orders using the same visual language as event invoices."""
from io import BytesIO
import os

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


FONT_REGULAR_PATH = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans.ttf")
FONT_BOLD_PATH = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans-Bold.ttf")
SUPPLIER_NAME = "Asociace klubů BMX, z.s."
SUPPLIER_STREET = "Korunní 972/75, Vinohrady"
SUPPLIER_CITY = "130 00 Praha 3"
SUPPLIER_COUNTRY = "Česká republika"
SUPPLIER_ICO = "07197896"


def _asset_path(*parts):
    candidates = [
        os.path.join(settings.BASE_DIR, "static", *parts),
        os.path.join(settings.BASE_DIR, "staticfiles", *parts),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


LOGO_PATH = _asset_path("images", "logo.png")


def _register_fonts():
    pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_REGULAR_PATH))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", FONT_BOLD_PATH))


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
        self.setFillColor(colors.HexColor("#64748B"))
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


def generate_invoice(order) -> BytesIO:
    """Return a BytesIO containing the PDF invoice for the given Order."""
    _register_fonts()
    order.ensure_invoice_number()
    return _generate_document(order, is_credit_note=False)


def generate_credit_note(order) -> BytesIO:
    """Return a BytesIO containing the PDF credit note for the given canceled order."""
    _register_fonts()
    order.ensure_invoice_number()
    order.ensure_credit_note_number()
    return _generate_document(order, is_credit_note=True)


def _generate_document(order, *, is_credit_note):
    buffer = BytesIO()
    pdf = NumberedCanvas(buffer, pagesize=A4)
    generated_at = order.updated.strftime("%d.%m.%Y %H:%M")
    footer_left = f"{'Dobropis' if is_credit_note else 'E-shop'} | Objednávka #{order.pk}"
    footer_right = f"Generováno {generated_at}"

    header_bottom_y = _draw_invoice_page_header(pdf, order, include_parties=True, is_credit_note=is_credit_note)
    table_top = header_bottom_y - 16 * mm
    _draw_invoice_table_header(pdf, order, table_top, is_credit_note=is_credit_note)

    current_y = table_top - 7 * mm
    bottom_limit = 30 * mm
    summary_reserved = 46 * mm

    items = list(order.items.select_related("variant__product").all())
    for item in items:
        description = _item_description(item)
        description_lines = simpleSplit(description, "DejaVuSans", 9, 116 * mm) or [description]
        row_height = max(8 * mm, (len(description_lines) * 4.6 * mm) + 2 * mm)

        if current_y - row_height < bottom_limit + summary_reserved:
            draw_pdf_footer(pdf, left_text=footer_left, right_text=footer_right)
            pdf.showPage()
            header_bottom_y = _draw_invoice_page_header(pdf, order, include_parties=False, is_credit_note=is_credit_note)
            table_top = header_bottom_y - 10 * mm
            _draw_invoice_table_header(pdf, order, table_top, is_credit_note=is_credit_note)
            current_y = table_top - 7 * mm

        pdf.setFillColor(colors.black)
        pdf.setFont("DejaVuSans", 9)
        text_y = current_y
        for description_line in description_lines:
            pdf.drawString(24 * mm, text_y, description_line)
            text_y -= 4.6 * mm
        pdf.drawRightString(187 * mm, current_y, f"{item.subtotal:.2f} Kč")
        current_y -= row_height

    if current_y - summary_reserved < bottom_limit:
        draw_pdf_footer(pdf, left_text=footer_left, right_text=footer_right)
        pdf.showPage()
        header_bottom_y = _draw_invoice_page_header(pdf, order, include_parties=False, is_credit_note=is_credit_note)
        table_top = header_bottom_y - 10 * mm
        _draw_invoice_table_header(pdf, order, table_top, is_credit_note=is_credit_note)
        current_y = table_top - 7 * mm

    _draw_invoice_summary(pdf, order, current_y, is_credit_note=is_credit_note)
    draw_pdf_footer(pdf, left_text=footer_left, right_text=footer_right)
    pdf.save()
    buffer.seek(0)
    return buffer


def _draw_invoice_page_header(pdf, order, include_parties=True, *, is_credit_note=False):
    width, height = A4
    header_x = 20 * mm
    header_y = height - 38 * mm

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

    document_number = _credit_note_number(order) if is_credit_note else _invoice_number(order)

    pdf.setFillColor(colors.black)
    pdf.setTitle(f"{'Dobropis' if is_credit_note else 'Faktura'} {document_number}")
    pdf.setFont("DejaVuSans-Bold", 18)
    pdf.drawString(header_x, header_y, f"{'Dobropis' if is_credit_note else 'Faktura'} č. {document_number}")

    pdf.setFont("DejaVuSans", 10)
    pdf.drawString(header_x, header_y - 12 * mm, f"Datum vystavení: {order.created:%d.%m.%Y}")
    pdf.drawString(
        header_x,
        header_y - 18 * mm,
        f"{'Datum storna' if is_credit_note else 'Datum úhrady'}: {order.updated:%d.%m.%Y}",
    )
    pdf.drawString(header_x, header_y - 24 * mm, f"Variabilní symbol: {order.pk}")

    if not include_parties:
        return header_y - 34 * mm

    pdf.setFont("DejaVuSans-Bold", 11)
    pdf.drawString(20 * mm, header_y - 44 * mm, "Dodavatel")
    pdf.drawString(110 * mm, header_y - 44 * mm, "Odběratel")

    pdf.setFont("DejaVuSans", 10)
    supplier_y = header_y - 52 * mm
    for line in _supplier_lines():
        pdf.drawString(20 * mm, supplier_y, line)
        supplier_y -= 5 * mm

    customer_y = header_y - 52 * mm
    for line in _customer_lines(order):
        pdf.drawString(110 * mm, customer_y, line)
        customer_y -= 5 * mm

    subject_y = min(supplier_y, customer_y) - 8 * mm
    pdf.setFont("DejaVuSans-Bold", 10)
    pdf.drawString(20 * mm, subject_y, "Předmět:")
    pdf.setFont("DejaVuSans", 10)
    subject_lines = simpleSplit(_subject_text(order, is_credit_note=is_credit_note), "DejaVuSans", 10, 146 * mm)
    for index, line in enumerate(subject_lines):
        pdf.drawString(40 * mm, subject_y - (index * 5 * mm), line)
    return subject_y - ((len(subject_lines) - 1) * 5 * mm)


def _draw_invoice_table_header(pdf, order, table_top, *, is_credit_note=False):
    pdf.setFillColor(colors.HexColor("#1E293B"))
    pdf.rect(20 * mm, table_top, 170 * mm, 8 * mm, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("DejaVuSans-Bold", 9)
    left_label = "Dobropisovaná položka" if is_credit_note else "Položka"
    if order.items.exists():
        if order.items.first().variant:
            left_label = f"{'Dobropisovaná položka' if is_credit_note else 'Položka'} / {order.items.first().variant.product.get_variant_type_display()}"
    pdf.drawString(24 * mm, table_top + 2.5 * mm, left_label)
    pdf.drawRightString(187 * mm, table_top + 2.5 * mm, "Cena")


def _draw_invoice_summary(pdf, order, current_y, *, is_credit_note=False):
    pdf.setFillColor(colors.black)
    current_y -= 6 * mm
    pdf.setFont("DejaVuSans-Bold", 10)
    pdf.drawString(
        20 * mm,
        current_y,
        "DOBROPIS VYSTAVEN, KREDIT VRÁCEN NA ÚČET" if is_credit_note else "NEPLAŤTE, UHRAZENO KREDITY Z ÚČTU",
    )
    current_y -= 4 * mm
    pdf.line(120 * mm, current_y, 190 * mm, current_y)
    current_y -= 7 * mm
    pdf.setFont("DejaVuSans-Bold", 11)
    pdf.drawRightString(152 * mm, current_y, "Dobropisovaná částka" if is_credit_note else "Celková částka")
    pdf.drawRightString(187 * mm, current_y, f"{order.total:.2f} Kč")
    current_y -= 7 * mm
    pdf.drawRightString(152 * mm, current_y, "Vráceno kredity" if is_credit_note else "Odečteno kredity")
    amount = int(order.total) if is_credit_note else (order.credits_charged or int(order.total))
    pdf.drawRightString(187 * mm, current_y, f"{amount:.2f} Kč")
    current_y -= 7 * mm
    pdf.drawRightString(152 * mm, current_y, "K úhradě" if not is_credit_note else "K doplacení")
    pdf.drawRightString(187 * mm, current_y, "0.00 Kč")
    current_y -= 12 * mm
    pdf.setFont("DejaVuSans", 9)
    pdf.drawString(
        20 * mm,
        current_y,
        "Dobropis byl vygenerován automaticky při stornu objednávky v e-shopu."
        if is_credit_note
        else "Faktura byla vygenerována automaticky po potvrzení objednávky v e-shopu.",
    )
    if order.note:
        note_lines = simpleSplit(f"Poznámka: {order.note}", "DejaVuSans", 9, 170 * mm)
        for index, line in enumerate(note_lines, start=1):
            pdf.drawString(20 * mm, current_y - index * 5 * mm, line)


def _invoice_number(order):
    return order.ensure_invoice_number()


def _credit_note_number(order):
    return order.ensure_credit_note_number()


def _supplier_lines():
    return [
        SUPPLIER_NAME,
        SUPPLIER_STREET,
        SUPPLIER_CITY,
        SUPPLIER_COUNTRY,
        f"IČ: {SUPPLIER_ICO}",
        "Nejsme plátci DPH",
    ]


def _customer_lines(order):
    lines = [
        f"{order.first_name} {order.last_name}",
        f"E-mail: {order.email}",
    ]
    if order.phone:
        lines.append(f"Telefon: {order.phone}")
    if order.street:
        lines.append(order.street)
    city_line = " ".join(part for part in [order.zip_code, order.city] if part)
    if city_line:
        lines.append(city_line)
    return lines


def _subject_text(order, *, is_credit_note=False):
    base = f"fakturujeme Vám objednávku z e-shopu Czech BMX č. {_invoice_number(order)}."
    if is_credit_note:
        return (
            f"stornujeme objednávku z e-shopu Czech BMX č. {_invoice_number(order)} "
            f"a vracíme kredit ve výši {int(order.total)} Kč zpět na účet zákazníka."
        )
    if order.event and order.event.date:
        return f"{base} Předání proběhne na závodě {order.event.name} dne {order.event.date:%d.%m.%Y}."
    if order.event:
        return f"{base} Předání proběhne na závodě {order.event.name}."
    return f"{base} Předání proběhne dle dohody."


def _item_description(item):
    if item.variant:
        variant_type = item.variant.product.get_variant_type_display()
        return (
            f"{item.variant.product.name} | {variant_type}: {item.variant.label} | "
            f"Počet kusů: {item.quantity} | Cena/ks: {item.unit_price:.2f} Kč"
        )
    return f"Produkt | Počet kusů: {item.quantity} | Cena/ks: {item.unit_price:.2f} Kč"
