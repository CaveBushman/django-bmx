"""Shared ReportLab building blocks for the project's PDF documents (invoices, receipts).

Keeps the supplier identity, font registration, page-numbering canvas and footer
in one place so the eshop and finance invoice generators stay visually consistent.
"""
import os

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


FONT_REGULAR_PATH = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans.ttf")
FONT_BOLD_PATH = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans-Bold.ttf")

SUPPLIER_NAME = "Asociace klubů BMX, z.s."
SUPPLIER_STREET = "Korunní 972/75, Vinohrady"
SUPPLIER_CITY = "130 00 Praha 3"
SUPPLIER_COUNTRY = "Česká republika"
SUPPLIER_COUNTRY_EN = "Czech Republic"
SUPPLIER_ICO = "07197896"

MUTED_TEXT_COLOR = colors.HexColor("#64748B")
DIVIDER_COLOR = colors.HexColor("#CBD5E1")


def register_fonts():
    """Register the DejaVu fonts with ReportLab (idempotent)."""
    registered = pdfmetrics.getRegisteredFontNames()
    if "DejaVuSans" not in registered:
        pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_REGULAR_PATH))
    if "DejaVuSans-Bold" not in registered:
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", FONT_BOLD_PATH))


class NumberedCanvas(canvas.Canvas):
    """Canvas that stamps a "Stránka X z Y" page number on every page."""

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
        self.setFillColor(MUTED_TEXT_COLOR)
        self.drawRightString(width - 20 * mm, 12 * mm, f"Stránka {page_number} z {page_count}")


def draw_pdf_footer(pdf, *, left_text="", right_text=""):
    width, _ = A4
    footer_y = 16 * mm
    pdf.setStrokeColor(DIVIDER_COLOR)
    pdf.line(20 * mm, footer_y + 4 * mm, width - 20 * mm, footer_y + 4 * mm)
    pdf.setFillColor(MUTED_TEXT_COLOR)
    pdf.setFont("DejaVuSans", 8)
    if left_text:
        pdf.drawString(20 * mm, footer_y, left_text)
    if right_text:
        pdf.drawRightString(width - 20 * mm, footer_y, right_text)
