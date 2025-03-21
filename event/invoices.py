from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Table, TableStyle
from django.conf import settings
from django.http import HttpResponse
import os
import datetime

def generate_invoice(request, event):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="faktura_.pdf"'
    
    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin = 2 * cm  # Nastavený okraj 2 cm ze všech stran
    
    # Fonty
    font_regular = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans.ttf")
    font_bold = os.path.join(settings.BASE_DIR, "static/fonts/DejaVuSans-Bold.ttf")
    pdfmetrics.registerFont(TTFont('DejaVuSans', font_regular))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', font_bold))
    
    # Logo v pravém horním rohu
    logo_path = os.path.join(settings.BASE_DIR, "static/images/logo.png")
    if os.path.exists(logo_path):
        p.drawImage(logo_path, width - margin - 100, height - margin - 50, width=100, height=50, preserveAspectRatio=True, mask='auto')
    
    # Záhlaví faktury
    p.setFont("DejaVuSans-Bold", 16)
    p.drawString(margin, height - margin - 10, "FAKTURA")
    
    # Informace o faktuře (datum a číslo) s menším písmem
    p.setFont("DejaVuSans", 10)
    p.drawString(margin, height - margin - 30, f"Číslo faktury: 12345")
    p.drawString(margin, height - margin - 45, f"Datum vystavení: {datetime.datetime.now().strftime('%d.%m.%Y')}")
    p.drawString(margin, height - margin - 60, f"Datum splatnosti: {datetime.datetime.now().strftime('%d.%m.%Y')}")
    
    # Mezera mezi záhlavím a informacemi o dodavateli
    y_position = height - margin - 160  # Posunuto, aby začalo o 5 cm níže než předtím
    
    # Informace o dodavateli a odběrateli (začínají na stejné výšce)
    supplier_info = [
        ["Dodavatel:", "Asociace klubů BMX, z.s."],
        ["Adresa:", "Korunní 972/75, 130 00 Praha 3"],
        ["IČO:", "07197896"],
        ["DIČ:", "CZ07197896"],
    ]
    
    customer_info = [
        ["Odběratel:", "Zákazník ABC"],
        ["Adresa:", "Ulice 456, Město, 67890"],
        ["IČO:", "87654321"],
        ["DIČ:", "CZ87654321"],
    ]
    
    def draw_info_table(data, x, y):
        table = Table(data, colWidths=[3 * cm, 11 * cm])  # Zúženo první sloupec, aby byl bližší k údajům
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),  # Zmenšení řádkování mezi řádky
            ('FONTSIZE', (0, 0), (-1, -1), 8),  # Zmenšení písma
            ('FONTNAME', (0, 0), (0, -1), 'DejaVuSans-Bold'),  # Tučné pro názvy polí
            ('FONTNAME', (1, 0), (1, -1), 'DejaVuSans'),  # Normální pro údaje
        ]))
        table.wrapOn(p, 0, 0)
        table.drawOn(p, x, y)
    
    # Zobrazíme tabulky pro dodavatele a odběratele ve stejné výšce
    draw_info_table(supplier_info, margin, y_position)
    draw_info_table(customer_info, width / 2, y_position)
    
    # Funkce pro dynamické dělení textu
    def split_text_to_lines(text, max_width, font_name='DejaVuSans', font_size=8):
        # Rozdělení textu na více řádků podle šířky
        lines = []
        current_line = ""
        p.setFont(font_name, font_size)
        for word in text.split():
            test_line = f"{current_line} {word}".strip()
            width_test = p.stringWidth(test_line)
            if width_test < max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines

    # Text pro položku
    item_description = "Startovné - Openseason 2025,  23.3.2025"
    
    # Získání šířky sloupce pro popis
    item_column_width = width - 4 * cm  # 100% šířky mezi okraji (2 cm z každé strany)
    max_width = item_column_width  # Maximální šířka pro popis položky
    
    # Rozdělení popisu na více řádků
    description_lines = split_text_to_lines(item_description, max_width)
    
    # Dynamické generování víceřádkové položky
    items = [
        ["Popis"],
    ]
    for line in description_lines:
        items.append([line])

    # Změna šířky tabulky tak, aby byla mezi okraji 2 cm
    table_width = width - 4 * cm  # 2 cm okraj z každé strany
    col_widths = [table_width]  # 100% pro popis

    table = Table(items, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),  # Pozadí pro záhlaví
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),  # Zarovnání doleva
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),  # Normální písmo
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),  # Pozadí pro tělo tabulky
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
    ]))
    
    table.wrapOn(p, 0, 0)
    table.drawOn(p, margin, y_position - 130)  # Zarovnáno na střed, s 2 cm okrajem
    
    # Celková částka a poznámka
    p.setFont("DejaVuSans-Bold", 14)
    p.drawRightString(width - margin, y_position - 200, f"Celkem: 1800 Kč")
    
    p.setFont("DejaVuSans-Bold", 12)
    p.setFillColor(colors.red)
    p.drawCentredString(width / 2, y_position - 230, "NEPLAŤTE - UHRAZENO")
    
    # Text "VYSTAVIL:" na konec faktury
    p.setFont("DejaVuSans", 8)
    p.setFillColor(colors.black)
    p.drawString(margin, y_position - 250, f"VYSTAVIL: Jméno osoby")
    
    p.showPage()
    p.save()
    
    return response