from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
import os
from datetime import date

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from bmx.pdf_utils import register_fonts
from event.models import EventType, Result

LOGO_PATH = os.path.join(settings.BASE_DIR, "static/images/logo.png")


@dataclass(frozen=True)
class PrizeMoneyCategoryConfig:
    code: str
    label: str
    amounts: tuple[int, ...]
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class PrizeMoneyScheme:
    categories: tuple[PrizeMoneyCategoryConfig, ...]
    allow_amount_toggle: bool = True


PRIZE_MONEY_SCHEMES = {
    EventType.MCR_JEDNOTLIVCU: PrizeMoneyScheme(
        categories=(
            PrizeMoneyCategoryConfig("EM", "Elite Men", (5000, 3000, 2000, 1400, 1200, 1000, 800, 600), ("Men Elite", "Elite Men", "EM")),
            PrizeMoneyCategoryConfig("EW", "Elite Women", (5000, 3000, 2000, 1400, 1200, 1000, 800, 600), ("Women Elite", "Elite Women", "EW")),
            PrizeMoneyCategoryConfig("U23M", "Men Under 23", (3000, 2000, 1500, 800, 700, 600, 500, 400), ("Men Under 23", "Men U23", "U23M", "U 23")),
            PrizeMoneyCategoryConfig("U23W", "Women Under 23", (3000, 2000, 1500, 800, 700, 600, 500, 400), ("Women Under 23", "Women U23", "U23W", "U 23")),
            PrizeMoneyCategoryConfig("JM", "Junior Men", (2000, 1000, 800, 600, 500, 400, 300, 200), ("Men Junior", "Junior Men", "JM", "Junior")),
            PrizeMoneyCategoryConfig("JW", "Junior Women", (2000, 1000, 800, 600, 500, 400, 300, 200), ("Women Junior", "Junior Women", "JW", "Junior")),
        ),
        allow_amount_toggle=True,
    ),
    EventType.CESKY_POHAR: PrizeMoneyScheme(
        categories=(
            PrizeMoneyCategoryConfig("EM", "Elite Men", (3750, 3125, 2500), ("Men Elite", "Elite Men", "EM")),
            PrizeMoneyCategoryConfig("EW", "Elite Women", (3750, 3125, 2500), ("Women Elite", "Elite Women", "EW")),
            PrizeMoneyCategoryConfig("U23M", "Men Under 23", (1625, 1375, 1000), ("Men Under 23", "Men U23", "U23M")),
            PrizeMoneyCategoryConfig("U23W", "Women Under 23", (1625, 1375, 1000), ("Women Under 23", "Women U23", "U23W")),
            PrizeMoneyCategoryConfig("JM", "Junior Men", (1000, 750, 500), ("Men Junior", "Junior Men", "JM")),
            PrizeMoneyCategoryConfig("JW", "Junior Women", (1000, 750, 500), ("Women Junior", "Junior Women", "JW")),
            PrizeMoneyCategoryConfig("B15/16", "Boys 15/16", (800, 500, 300), ("Boys 15 and 16", "Boys 15-16", "B15/16")),
            PrizeMoneyCategoryConfig("M17+", "Men 17+", (800, 500, 300), ("Men 17+", "M17+")),
            PrizeMoneyCategoryConfig("G16+", "Girls/Women 16+", (800, 500, 300), ("Girls 16 and over", "G16+", "Girls/Women 16+")),
        ),
        allow_amount_toggle=True,
    ),
    EventType.CESKA_LIGA: PrizeMoneyScheme(
        categories=(
            PrizeMoneyCategoryConfig("B15/16", "Boys 15/16", (800, 500, 300), ("Boys 15 and 16", "Boys 15-16", "B15/16")),
            PrizeMoneyCategoryConfig("M17+", "Men 17+", (800, 500, 300), ("Men 17+", "M17+")),
        ),
        allow_amount_toggle=False,
    ),
    EventType.MORAVSKA_LIGA: PrizeMoneyScheme(
        categories=(
            PrizeMoneyCategoryConfig("B15/16", "Boys 15/16", (800, 500, 300), ("Boys 15 and 16", "Boys 15-16", "B15/16")),
            PrizeMoneyCategoryConfig("M17+", "Men 17+", (800, 500, 300), ("Men 17+", "M17+")),
        ),
        allow_amount_toggle=False,
    ),
}


def _normalize_category(value):
    return (value or "").strip().lower()


def _resolve_rider_class_20_for_event(rider, event_date):
    if not rider or not event_date or not rider.date_of_birth:
        return ""

    age = event_date.year - rider.date_of_birth.year

    if rider.is_elite:
        if rider.gender in {"Muž", "Ostatní"}:
            if age <= 18:
                return "Men Junior"
            if age <= 22:
                return "Men Under 23"
            return "Men Elite"
        if age <= 18:
            return "Women Junior"
        if age <= 22:
            return "Women Under 23"
        return "Women Elite"

    if rider.gender in {"Muž", "Ostatní"}:
        if age <= 6:
            return "Boys 6"
        if age == 7:
            return "Boys 7"
        if age == 8:
            return "Boys 8"
        if age == 9:
            return "Boys 9"
        if age == 10:
            return "Boys 10"
        if age == 11:
            return "Boys 11"
        if age == 12:
            return "Boys 12"
        if age == 13:
            return "Boys 13"
        if age == 14:
            return "Boys 14"
        if age == 15:
            return "Boys 15"
        if age == 16:
            return "Boys 16"
        if age <= 24:
            return "Men 17-24"
        if age <= 29:
            return "Men 25-29"
        if age <= 34:
            return "Men 30-34"
        return "Men 35 and over"

    if age <= 6:
        return "Girls 6"
    if age == 7:
        return "Girls 7"
    if age == 8:
        return "Girls 8"
    if age == 9:
        return "Girls 9"
    if age == 10:
        return "Girls 10"
    if age == 11:
        return "Girls 11"
    if age == 12:
        return "Girls 12"
    if age == 13:
        return "Girls 13"
    if age == 14:
        return "Girls 14"
    if age == 15:
        return "Girls 15"
    if age == 16:
        return "Girls 16"
    if age <= 24:
        return "Women 17-24"
    return "Women 25 and over"


class PrizeMoneyPdfService:
    def __init__(self):
        register_fonts()
        styles = getSampleStyleSheet()
        self.styles = {
            "meta": ParagraphStyle(
                "PrizeMeta",
                parent=styles["Normal"],
                fontName="DejaVuSans",
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#475569"),
            ),
            "title": ParagraphStyle(
                "PrizeTitle",
                parent=styles["Heading1"],
                fontName="DejaVuSans-Bold",
                fontSize=18,
                leading=22,
                textColor=colors.HexColor("#0f172a"),
                alignment=TA_CENTER,
                spaceAfter=6,
            ),
            "section": ParagraphStyle(
                "PrizeSection",
                parent=styles["Heading2"],
                fontName="DejaVuSans-Bold",
                fontSize=12,
                leading=16,
                textColor=colors.HexColor("#1e293b"),
                spaceAfter=8,
                spaceBefore=10,
            ),
            "note": ParagraphStyle(
                "PrizeNote",
                parent=styles["Normal"],
                fontName="DejaVuSans",
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#64748b"),
                spaceAfter=6,
            ),
        }

    def get_scheme(self, event):
        return PRIZE_MONEY_SCHEMES.get(event.type_for_ranking, ())

    def allows_amount_toggle(self, event):
        scheme = self.get_scheme(event)
        return bool(scheme and scheme.allow_amount_toggle)

    def _results_by_category(self, event):
        results = (
            Result.objects.filter(event=event)
            .select_related("rider")
            .order_by("category", "place")
        )
        grouped = defaultdict(list)
        for result in results:
            grouped[_normalize_category(result.category)].append(result)
        return grouped

    def _results_by_rider_class_20(self, event):
        results = (
            Result.objects.filter(event=event, is_20=True)
            .select_related("rider")
            .order_by("place")
        )
        grouped = defaultdict(list)
        for result in results:
            rider_class_20 = _resolve_rider_class_20_for_event(result.rider, event.date or date.today())
            if not rider_class_20:
                continue
            grouped[_normalize_category(rider_class_20)].append(result)
        return grouped

    def _aliases_to_category_map(self, scheme):
        alias_map = {}
        for config in scheme.categories:
            for alias in config.aliases:
                alias_map[_normalize_category(alias)] = _normalize_category(config.aliases[0])
        return alias_map

    def _results_by_mcr_prize_category(self, event, scheme):
        results = (
            Result.objects.filter(event=event, is_20=True)
            .select_related("rider")
            .order_by("place")
        )
        alias_map = self._aliases_to_category_map(scheme)
        grouped = defaultdict(list)
        assigned_riders = set()
        for result in results:
            rider_key = result.rider_id or f"name:{(result.first_name or '').strip().lower()}:{(result.last_name or '').strip().lower()}"
            if rider_key in assigned_riders:
                continue

            result_category_key = alias_map.get(_normalize_category(result.category))
            if result_category_key:
                grouped[result_category_key].append(result)
                assigned_riders.add(rider_key)
                continue

            rider_class_20 = _resolve_rider_class_20_for_event(result.rider, event.date or date.today())
            rider_category_key = alias_map.get(_normalize_category(rider_class_20))
            if rider_category_key:
                grouped[rider_category_key].append(result)
                assigned_riders.add(rider_key)
        return grouped

    def _resolve_category_results(self, config, results_by_category):
        for alias in config.aliases:
            normalized = _normalize_category(alias)
            alias_results = results_by_category.get(normalized)
            if alias_results:
                return alias, alias_results
        return None, []

    def _resolve_category_results_from_rider_class(self, config, results_by_rider_class):
        for alias in config.aliases:
            normalized = _normalize_category(alias)
            alias_results = results_by_rider_class.get(normalized)
            if alias_results:
                return alias, alias_results
        return None, []

    def _build_rows(self, results, amounts, include_amounts, use_category_order=False):
        ordered_results = list(results)
        if use_category_order:
            ordered_results.sort(
                key=lambda result: (
                    result.place if result.place is not None else 9999,
                    (result.last_name or "").lower(),
                    (result.first_name or "").lower(),
                )
            )
        else:
            ordered_results = sorted(
                [result for result in ordered_results if result.place is not None],
                key=lambda result: result.place,
            )
        results_by_place = {result.place: result for result in ordered_results if result.place is not None}
        rows = []
        for index, place in enumerate(range(1, len(amounts) + 1), start=0):
            if use_category_order:
                result = ordered_results[index] if index < len(ordered_results) else None
            else:
                result = results_by_place.get(place)
            rider_name = ""
            uci_id = ""
            if result:
                if result.rider:
                    rider_name = " ".join(
                        part for part in [result.rider.first_name, result.rider.middle_name, result.rider.last_name] if part
                    ).strip()
                else:
                    rider_name = " ".join(part for part in [result.first_name, result.last_name] if part).strip()
                uci_id = result.rider_id or ""
            row = [str(place), rider_name, uci_id]
            if include_amounts:
                row.append(f"{amounts[index]:,} Kč".replace(",", " "))
            row.append("")
            rows.append(row)
        return rows

    def _on_page(self, event, include_amounts):
        logo_reader = ImageReader(LOGO_PATH) if os.path.exists(LOGO_PATH) else None

        def draw(canvas, doc):
            canvas.saveState()
            width, height = landscape(A4)
            if logo_reader:
                canvas.drawImage(
                    logo_reader,
                    width - doc.rightMargin - 34 * mm,
                    height - 22 * mm,
                    width=28 * mm,
                    height=14 * mm,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            canvas.setFont("DejaVuSans-Bold", 16)
            canvas.drawString(doc.leftMargin, height - 16 * mm, "Potvrzení převzetí prize money")
            canvas.setFont("DejaVuSans", 10)
            subtitle = "Varianta s částkami" if include_amounts else "Varianta bez částek"
            canvas.drawString(doc.leftMargin, height - 22 * mm, subtitle)
            canvas.line(doc.leftMargin, height - 25 * mm, width - doc.rightMargin, height - 25 * mm)
            canvas.setFont("DejaVuSans", 9)
            canvas.drawRightString(width - doc.rightMargin, 8 * mm, f"Strana {doc.page}")
            canvas.restoreState()

        return draw

    def build_pdf(self, event, include_amounts=True):
        scheme = self.get_scheme(event)
        if not scheme:
            raise ValueError(f"Pro typ závodu '{event.type_for_ranking}' není nastavena prize money šablona.")

        if not scheme.allow_amount_toggle:
            include_amounts = True

        results_by_category = self._results_by_category(event)
        results_by_rider_class = None
        use_category_order = False
        if event.type_for_ranking == EventType.MCR_JEDNOTLIVCU:
            results_by_rider_class = self._results_by_mcr_prize_category(event, scheme)
            use_category_order = True

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=34 * mm,
            bottomMargin=14 * mm,
        )

        story = []
        event_date = event.date.strftime("%d.%m.%Y") if event.date else "-"
        organizer = getattr(event.organizer, "team_name", "") or "-"

        story.append(Paragraph(event.name, self.styles["title"]))
        story.append(Paragraph(f"Pořadatel: {organizer}<br/>Datum závodu: {event_date}", self.styles["meta"]))
        story.append(Spacer(1, 6 * mm))

        for config in scheme.categories:
            if results_by_rider_class is not None:
                source_label, matched_results = self._resolve_category_results_from_rider_class(config, results_by_rider_class)
                if not matched_results:
                    source_label, matched_results = self._resolve_category_results(config, results_by_category)
            else:
                source_label, matched_results = self._resolve_category_results(config, results_by_category)
            section_title = f"{config.code} - {config.label}"
            block = [Paragraph(section_title, self.styles["section"])]
            if source_label:
                block.append(Paragraph(f"Zdroj výsledků: {source_label}", self.styles["note"]))
            else:
                block.append(Paragraph("Výsledky se do této kategorie nepodařilo automaticky doplnit.", self.styles["note"]))

            header = ["Umístění", "Jméno a příjmení", "UCI ID"]
            col_widths = [24 * mm, 72 * mm, 42 * mm]
            if include_amounts:
                header.append("Částka")
                col_widths.append(28 * mm)
            header.append("Podpis")
            col_widths.append(86 * mm if include_amounts else 114 * mm)

            table_data = [header] + self._build_rows(
                matched_results,
                config.amounts,
                include_amounts,
                use_category_order=use_category_order,
            )
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "DejaVuSans-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "DejaVuSans"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 12),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (2, -1), "CENTER"),
                ("ALIGN", (3, 1), (3, -1), "CENTER") if include_amounts else ("ALIGN", (2, 1), (2, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            block.append(table)
            block.append(Spacer(1, 4 * mm))
            story.append(KeepTogether(block))

        doc.build(story, onFirstPage=self._on_page(event, include_amounts), onLaterPages=self._on_page(event, include_amounts))
        return buffer.getvalue()
