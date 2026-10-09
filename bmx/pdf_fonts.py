"""DejaVu fonty pro ReportLab PDF (faktury, účtenky, reporty) — s diakritikou."""
import os

from django.conf import settings
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_REGULAR_PATH = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans.ttf")
FONT_BOLD_PATH = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans-Bold.ttf")


def register_pdf_fonts():
    """Zaregistruje DejaVuSans a DejaVuSans-Bold, pokud ještě nejsou registrované."""
    registered = pdfmetrics.getRegisteredFontNames()
    if "DejaVuSans" not in registered:
        pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_REGULAR_PATH))
    if "DejaVuSans-Bold" not in registered:
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", FONT_BOLD_PATH))
