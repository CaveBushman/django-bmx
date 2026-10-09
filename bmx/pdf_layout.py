"""Společné prvky A4 dokladů v ReportLabu: číslování stránek a patička."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

FOOTER_TEXT_COLOR = colors.HexColor("#64748B")
FOOTER_LINE_COLOR = colors.HexColor("#CBD5E1")


class NumberedCanvas(canvas.Canvas):
    """Canvas, který na každou stránku dopíše „Stránka X z Y“ (počet zná až při save)."""

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
        self.setFillColor(FOOTER_TEXT_COLOR)
        self.drawRightString(width - 20 * mm, 12 * mm, f"Stránka {page_number} z {page_count}")


def draw_pdf_footer(pdf, *, left_text="", right_text=""):
    width, _ = A4
    footer_y = 16 * mm
    pdf.setStrokeColor(FOOTER_LINE_COLOR)
    pdf.line(20 * mm, footer_y + 4 * mm, width - 20 * mm, footer_y + 4 * mm)
    pdf.setFillColor(FOOTER_TEXT_COLOR)
    pdf.setFont("DejaVuSans", 8)
    if left_text:
        pdf.drawString(20 * mm, footer_y, left_text)
    if right_text:
        pdf.drawRightString(width - 20 * mm, footer_y, right_text)
