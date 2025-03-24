from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from django.http import HttpResponse
import io
import os

# Načtení fontu DejaVuSans
FONT_PATH = os.path.join("static", "fonts", "DejaVuSans.ttf")
pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))

def generate_invoice_pdf(invoice_data):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("DejaVuSans", 14)
    c.drawString(30 * mm, height - 30 * mm, f"Faktura - daňový doklad č. {invoice_data['number']}")

    # Dodavatel
    c.setFont("DejaVuSans", 10)
    c.drawString(30 * mm, height - 40 * mm, "Dodavatel:")
    y = height - 45 * mm
    for line in invoice_data["supplier"]:
        c.drawString(30 * mm, y, line)
        y -= 5 * mm

    # Odběratel
    c.drawString(110 * mm, height - 40 * mm, "Odběratel:")
    y = height - 45 * mm
    for line in invoice_data["customer"]:
        c.drawString(110 * mm, y, line)
        y -= 5 * mm

    # Informace o platbě
    c.drawString(30 * mm, y - 5 * mm, f"Datum vystavení: {invoice_data['issue_date']}")
    c.drawString(30 * mm, y - 10 * mm, f"Datum splatnosti: {invoice_data['due_date']}")
    c.drawString(30 * mm, y - 15 * mm, f"Způsob platby: {invoice_data['payment_method']}")
    c.drawString(30 * mm, y - 20 * mm, f"Variabilní symbol: {invoice_data['vs']}")
    c.drawString(30 * mm, y - 25 * mm, f"Bankovní účet: {invoice_data['iban']}")

    # Tabulka položek
    c.setFont("DejaVuSans", 10)
    y -= 40 * mm
    c.drawString(30 * mm, y, "Popis")
    c.drawString(100 * mm, y, "Počet")
    c.drawString(120 * mm, y, "Cena/ks")
    c.drawString(145 * mm, y, "DPH")
    c.drawString(170 * mm, y, "Celkem")
    y -= 5 * mm
    c.line(25 * mm, y, 190 * mm, y)

    for item in invoice_data["items"]:
        y -= 8 * mm
        c.drawString(30 * mm, y, item["description"])
        c.drawString(100 * mm, y, f'{item["qty"]}')
        c.drawString(120 * mm, y, f'{item["unit_price"]:.2f} Kč')
        c.drawString(145 * mm, y, f'{item["vat"]} %')
        c.drawString(170 * mm, y, f'{item["total"]:.2f} Kč')

    # Souhrn
    y -= 20 * mm
    c.setFont("DejaVuSans", 10)
    c.drawString(30 * mm, y, "Souhrn DPH")
    y -= 5 * mm
    c.drawString(30 * mm, y, f"Základ: {invoice_data['summary']['base']:.2f} Kč")
    y -= 5 * mm
    c.drawString(30 * mm, y, f"DPH: {invoice_data['summary']['vat']:.2f} Kč")
    y -= 5 * mm
    c.drawString(30 * mm, y, f"Celkem: {invoice_data['summary']['total']:.2f} Kč")

    # Výzva k úhradě
    y -= 20 * mm
    c.setFont("DejaVuSans", 9)
    c.drawString(30 * mm, y, "Dovolujeme si Vás upozornit, že v případě nedodržení data splatnosti může být účtován zákonný úrok z prodlení.")

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer