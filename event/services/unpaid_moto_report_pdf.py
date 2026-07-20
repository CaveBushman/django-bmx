from io import BytesIO
import os

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from bmx.pdf_utils import register_fonts


ASSOCIATION_LOGO_PATH = os.path.join(settings.BASE_DIR, "static/images/logo.png")


class UnpaidMotoReportPdfService:
    def build_pdf(self, event, report):
        register_fonts()
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "report_title",
            parent=styles["Heading1"],
            fontName="DejaVuSans-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=8,
        )
        body_style = ParagraphStyle(
            "report_body",
            parent=styles["BodyText"],
            fontName="DejaVuSans",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#475569"),
        )
        section_style = ParagraphStyle(
            "report_section",
            parent=styles["Heading2"],
            fontName="DejaVuSans-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=8,
            spaceAfter=6,
        )

        story = [
            Paragraph(_("Kontrola startovného podle MOTO"), title_style),
            Paragraph(event.name, title_style),
            Paragraph(
                _(
                    "Sestava porovnává jezdce z MOTO jízd v RaceRun s uhrazenými online registracemi. "
                    "Záznamy bez UCI ID jsou vedené zvlášť pro ruční kontrolu."
                ),
                body_style,
            ),
            Spacer(1, 8),
            Paragraph(
                _(
                    "Jezdci v MOTO: %(moto)s | Uhrazené online registrace: %(paid)s | Podezřelé neshody: %(flagged)s"
                )
                % {
                    "moto": report["moto_riders_count"],
                    "paid": report["paid_entries_count"],
                    "flagged": report["flagged_count"],
                },
                body_style,
            ),
            Spacer(1, 12),
        ]

        story.extend(
            self._build_section(
                _("Jezdci bez uhrazeného startovného"),
                [_("Příjmení"), _("Jméno"), _("UCI ID"), _("Startovní číslo"), _("Kategorie")],
                [
                    [row.last_name or "-", row.first_name or "-", row.uci_id or "-", row.plate or "-", row.category or "-"]
                    for row in report["confirmed_unpaid"]
                ],
                _("Nebyla nalezena žádná jistá neshoda."),
                section_style,
                body_style,
                [48 * mm, 42 * mm, 40 * mm, 34 * mm, 64 * mm],
            )
        )

        story.extend(
            self._build_section(
                _("Záznamy bez UCI ID"),
                [_("Příjmení"), _("Jméno"), _("Startovní číslo"), _("Kategorie")],
                [
                    [row.last_name or "-", row.first_name or "-", row.plate or "-", row.category or "-"]
                    for row in report["missing_uci"]
                ],
                _("Žádné problematické záznamy bez UCI ID nebyly nalezeny."),
                section_style,
                body_style,
                [58 * mm, 48 * mm, 38 * mm, 96 * mm],
            )
        )

        doc.build(story, onFirstPage=self._draw_page_header, onLaterPages=self._draw_page_header)
        return buffer.getvalue()

    def build_filename(self, event):
        timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
        return f"unpaid-moto-riders-{event.id}-{timestamp}.pdf"

    def _build_section(self, title, headers, rows, empty_text, section_style, body_style, col_widths):
        story = [Paragraph(title, section_style)]
        if not rows:
            story.extend([Paragraph(empty_text, body_style), Spacer(1, 10)])
            return story

        table_data = [headers] + rows
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "DejaVuSans-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "DejaVuSans"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#64748b")),
                    ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#334155")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fcfdff")]),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.extend([table, Spacer(1, 10)])
        return story

    def _draw_page_header(self, canvas, doc):
        if not os.path.exists(ASSOCIATION_LOGO_PATH):
            return

        canvas.saveState()
        logo_width = 22 * mm
        logo_height = 22 * mm
        x = doc.pagesize[0] - doc.rightMargin - logo_width
        y = doc.pagesize[1] - 9 * mm - logo_height
        canvas.drawImage(
            ASSOCIATION_LOGO_PATH,
            x,
            y,
            width=logo_width,
            height=logo_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        canvas.restoreState()
