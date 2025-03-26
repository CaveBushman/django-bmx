from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
import os

# Registrace fontů
BASE_FONT_PATH = os.path.join("static", "fonts")
pdfmetrics.registerFont(TTFont("DejaVuSans", os.path.join(BASE_FONT_PATH, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", os.path.join(BASE_FONT_PATH, "DejaVuSans-Bold.ttf")))

def generate_invoice_pdf(invoice_data):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)

    # Nadpis
    c.setFont("DejaVuSans-Bold", 14)
    c.drawString(20 * mm, height - 20 * mm, f"Faktura - daňový doklad č. {invoice_data['number']}")

    # Dodavatel
    c.setFont("DejaVuSans", 10)
    c.drawString(20 * mm, height - 30 * mm, "Dodavatel:")
    y = height - 36 * mm
    for line in invoice_data["supplier"]:
        c.drawString(20 * mm, y, line)
        y -= 5 * mm

    # Odběratel
    c.drawString(100 * mm, height - 30 * mm, "Odběratel:")
    y2 = height - 36 * mm
    for line in invoice_data["customer"]:
        c.drawString(100 * mm, y2, line)
        y2 -= 5 * mm

    # Platební informace
    y_info = min(y, y2) - 5 * mm
    info_lines = [
        f"Datum vystavení: {invoice_data['issue_date']}",
        f"Datum splatnosti: {invoice_data['due_date']}",
        f"Způsob platby: {invoice_data['payment_method']}",
        f"Variabilní symbol: {invoice_data['vs']}",
        f"Bankovní účet: {invoice_data['iban']}",
    ]
    for line in info_lines:
        c.drawString(20 * mm, y_info, line)
        y_info -= 5 * mm

    # Tabulka položek
    y_table = y_info - 10 * mm
    c.setFont("DejaVuSans-Bold", 10)
    c.drawString(20 * mm, y_table, "Popis")
    c.drawString(120 * mm, y_table, "Počet")
    c.drawString(140 * mm, y_table, "Cena/ks")
    c.drawString(170 * mm, y_table, "DPH")
    c.drawString(190 * mm, y_table, "Celkem")
    c.line(20 * mm, y_table - 2 * mm, 270 * mm, y_table - 2 * mm)

    y_table -= 8 * mm
    c.setFont("DejaVuSans", 10)
    for item in invoice_data["items"]:
        c.drawString(20 * mm, y_table, item["description"])
        c.drawRightString(135 * mm, y_table, str(item["qty"]))
        c.drawRightString(165 * mm, y_table, f"{item['unit_price']:.2f} Kč")
        c.drawRightString(185 * mm, y_table, f"{item['vat']} %")
        c.drawRightString(210 * mm, y_table, f"{item['total']:.2f} Kč")
        y_table -= 6 * mm

    # Souhrn DPH
    y_table -= 10 * mm
    c.setFont("DejaVuSans-Bold", 10)
    c.drawString(20 * mm, y_table, "Souhrn DPH")
    c.setFont("DejaVuSans", 10)
    y_table -= 5 * mm
    c.drawString(20 * mm, y_table, f"Základ: {invoice_data['summary']['base']:.2f} Kč")
    y_table -= 5 * mm
    c.drawString(20 * mm, y_table, f"DPH: {invoice_data['summary']['vat']:.2f} Kč")
    y_table -= 5 * mm
    c.drawString(20 * mm, y_table, f"Celkem: {invoice_data['summary']['total']:.2f} Kč")

    # Výzva k úhradě
    y_table -= 10 * mm
    c.setFont("DejaVuSans", 9)
    c.drawString(20 * mm, y_table, "Dovolujeme si Vás upozornit, že v případě nedodržení data splatnosti může být účtován zákonný úrok z prodlení.")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer