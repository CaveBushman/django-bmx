"""Generování PDF reportu s prémiovými statistikami jezdce (reportlab)."""

from io import BytesIO
import os
import re

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from bmx.pdf_utils import register_fonts


LOGO_PATH = os.path.join(settings.BASE_DIR, "static/images/logo.png")

PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
LEFT_MARGIN = 1.6 * cm
RIGHT_MARGIN = 1.6 * cm
TOP_MARGIN = 1.2 * cm
BOTTOM_MARGIN = 1.0 * cm

SLATE_900 = colors.HexColor("#0f172a")
SLATE_700 = colors.HexColor("#334155")
SLATE_500 = colors.HexColor("#64748b")
SLATE_300 = colors.HexColor("#cbd5e1")
SLATE_200 = colors.HexColor("#e2e8f0")
SLATE_100 = colors.HexColor("#f1f5f9")
WHITE = colors.white
INDIGO = colors.HexColor("#4338ca")
TEAL = colors.HexColor("#0f766e")
ORANGE = colors.HexColor("#ea580c")

PRIMARY_STATS = [
    ("starts_count", _("Starty"), 0, ""),
    ("runs_count", _("Měřené jízdy"), 0, ""),
    ("final_rate", _("Final rate"), 0, "%"),
    ("podium_rate", _("Podium rate"), 0, "%"),
    ("best_result", _("Nejlepší výsledek"), 0, ""),
    ("median_result", _("Medián výsledků"), 1, ""),
    ("median_finish_time", _("Medián cíle"), 3, " s"),
    ("median_hill_time", _("Medián startu"), 3, " s"),
    ("median_split_1", _("Medián Inter2"), 3, " s"),
    ("best_finish_time", _("Nejlepší cíl"), 3, " s"),
    ("best_hill_time", _("Nejlepší start"), 3, " s"),
    ("best_split_1", _("Nejlepší Inter2"), 3, " s"),
]

DETAIL_SECTIONS = [
    (
        _("Výsledky a umístění"),
        [
            ("total_starts_count", _("Celkem závodů na trati"), 0, ""),
            ("recent_track_results_count", _("Výsledky v KPI období"), 0, ""),
            ("recent_track_runs_count", _("Jízdy v KPI období"), 0, ""),
            ("final_runs_count", _("Finálové jízdy"), 0, ""),
            ("progressed_events_count", _("Postupů do dalších kol"), 0, ""),
            ("progression_rate", _("Postupovost"), 0, "%"),
            ("average_moto_place", _("Průměr moto umístění"), 2, ""),
            ("average_final_place", _("Průměr finálového umístění"), 2, ""),
            ("win_rate", _("Win rate"), 0, "%"),
        ],
    ),
    (
        _("Časy a start"),
        [
            ("average_finish_time", _("Průměrný cíl"), 3, " s"),
            ("finish_time_stddev", _("Rozptyl cílových časů"), 3, " s"),
            ("average_hill_rank", _("Průměrné pořadí na hillu"), 2, ""),
            ("hill_win_rate", _("Hill win rate"), 0, "%"),
            ("hill_top3_rate", _("Hill top3 rate"), 0, "%"),
            ("average_positions_gained_after_hill", _("Zisk pozic po startu"), 2, ""),
            ("hill_rankable_runs_count", _("Jízdy s hill pořadím"), 0, ""),
            ("best_hill_lane", _("Nejrychlejší dráha pro start"), None, ""),
            ("best_hill_lane_median", _("Medián nejlepší dráhy"), 3, " s"),
            ("best_result_lane", _("Nejlepší dráha pro výsledek"), None, ""),
            ("best_result_lane_average", _("Průměrné umístění nejlepší dráhy"), 2, ""),
        ],
    ),
    (
        _("Skóre a profil"),
        [
            ("conversion_score", _("Konverze"), 0, "%"),
            ("recovery_score", _("Návrat"), 0, "%"),
            ("pressure_score", _("Tlak"), 0, ""),
            ("pressure_delta", _("Rozdíl tlaku"), 2, ""),
            ("track_affinity_score", _("Track affinity score"), 0, ""),
            ("track_affinity_delta", _("Rozdíl affinity"), 2, ""),
            ("track_affinity_label", _("Affinity tratě"), None, ""),
            ("stability_score", _("Stability score"), 0, ""),
            ("risk_score", _("Riziko"), 0, ""),
            ("consistency_score", _("Consistency score"), 0, ""),
            ("consistency_label", _("Konzistence"), None, ""),
        ],
    ),
    (
        _("Spolehlivost a peer group"),
        [
            ("bad_status_count", _("Problematické jízdy"), 0, ""),
            ("clean_run_rate", _("Čisté jízdy"), 0, "%"),
            ("pace_index", _("Pace index"), 1, ""),
            ("peer_group_size", _("Velikost peer group"), 0, ""),
            ("peer_place_percentile", _("Percentil pořadí"), 0, "%"),
            ("peer_finish_percentile", _("Percentil času"), 0, "%"),
            ("trend_label", _("Trend"), None, ""),
            ("trend_delta", _("Rozdíl trendu"), 3, " s"),
            ("trend_detail", _("Detail trendu"), None, ""),
            ("peer_label", _("Peer group"), None, ""),
        ],
    ),
]


def _get_logo_reader():
    if os.path.exists(LOGO_PATH):
        return ImageReader(LOGO_PATH)
    return None


def _sanitize_filename(value):
    normalized = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return normalized or "premium-stats"


def _format_value(value, digits=2, suffix=""):
    if value in (None, ""):
        return "-"
    if isinstance(value, float):
        rendered = f"{value:.{digits}f}".replace(".", ",")
    else:
        rendered = str(value)
    return f"{rendered}{suffix}"


def build_rider_premium_stats_pdf(rider, track, track_stats, kpi_period):
    register_fonts()
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    pdf.setTitle(f"Premium statistiky {rider.first_name} {rider.last_name}")

    _draw_summary_page(pdf, rider, track, track_stats, kpi_period)
    _draw_detail_page(pdf, rider, track, track_stats)
    _draw_event_tables_page(pdf, rider, track, track_stats)
    _draw_chart_page(
        pdf,
        rider=rider,
        track=track,
        wheel=track_stats.get("wheel"),
        page_title=_("Medián cílových časů podle závodu"),
        section_label=_("Finish time"),
        points=track_stats.get("chart_points") or [],
        y_ticks=track_stats.get("chart_y_ticks") or [],
        min_time=track_stats.get("chart_min_time"),
        max_time=track_stats.get("chart_max_time"),
        line_color=INDIGO,
        empty_message=_("Pro vykreslení trendu zatím nejsou na této trati dostupné časy závodů."),
    )
    _draw_chart_page(
        pdf,
        rider=rider,
        track=track,
        wheel=track_stats.get("wheel"),
        page_title=_("Medián startových časů podle závodu"),
        section_label=_("Hill time"),
        points=track_stats.get("start_chart_points") or [],
        y_ticks=track_stats.get("start_chart_y_ticks") or [],
        min_time=track_stats.get("start_chart_min_time"),
        max_time=track_stats.get("start_chart_max_time"),
        line_color=TEAL,
        empty_message=_("Pro vykreslení trendu startových časů zatím nejsou na této trati dostupná data."),
    )
    _draw_chart_page(
        pdf,
        rider=rider,
        track=track,
        wheel=track_stats.get("wheel"),
        page_title=_("Medián mezičasů Inter2 podle závodu"),
        section_label=_("Split 1"),
        points=track_stats.get("split_chart_points") or [],
        y_ticks=track_stats.get("split_chart_y_ticks") or [],
        min_time=track_stats.get("split_chart_min_time"),
        max_time=track_stats.get("split_chart_max_time"),
        line_color=ORANGE,
        empty_message=_("Pro vykreslení trendu Inter2 zatím nejsou na této trati dostupná data."),
    )

    pdf.save()
    return buffer.getvalue()


def build_rider_premium_stats_pdf_filename(rider, track):
    rider_slug = _sanitize_filename(f"{rider.first_name}-{rider.last_name}")
    track_slug = _sanitize_filename(getattr(track, "name", "") or "track")
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"premium-stats-{rider_slug}-{track_slug}-{timestamp}.pdf"


def _draw_summary_page(pdf, rider, track, track_stats, kpi_period):
    _start_page(
        pdf,
        report_title=_("Premium Statistics Report"),
        page_title=f"{rider.first_name} {rider.last_name}",
        section_label="",
    )

    meta_top = PAGE_HEIGHT - TOP_MARGIN - 3.4 * cm
    left_w = 8.4 * cm
    gap = 0.6 * cm
    right_w = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN - left_w - gap

    _draw_info_box(
        pdf,
        LEFT_MARGIN,
        meta_top,
        left_w,
        _("Rider"),
        [
            _("Jméno: %(value)s") % {"value": f"{rider.first_name} {rider.last_name}"},
            _("UCI ID: %(value)s") % {"value": rider.uci_id},
            _("Klub: %(value)s") % {"value": getattr(rider.club, "team_name", "-") or "-"},
        ],
    )
    _draw_info_box(
        pdf,
        LEFT_MARGIN + left_w + gap,
        meta_top,
        right_w,
        _("Export"),
        [
            _("Trať: %(value)s") % {"value": _get_track_name(track)},
            _("Disciplína: %(value)s") % {"value": f'{track_stats.get("wheel") or "-"}"'},
            _("KPI období: %(value)s") % {"value": kpi_period.get("label") or "-"},
        ],
    )

    stats = [
        (label, _render_metric_value(track_stats.get(key), digits=digits, suffix=suffix))
        for key, label, digits, suffix in PRIMARY_STATS
    ]

    cols = 4
    card_gap = 0.45 * cm
    card_width = (PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN - card_gap * (cols - 1)) / cols
    card_height = 2.6 * cm
    cards_top = meta_top - 4.2 * cm

    for index, (label, value) in enumerate(stats):
        row = index // cols
        col = index % cols
        x = LEFT_MARGIN + col * (card_width + card_gap)
        y = cards_top - row * (card_height + card_gap)
        _draw_stat_card(pdf, x, y, card_width, card_height, label, value)

    note_y = BOTTOM_MARGIN + 0.4 * cm
    pdf.setFont("DejaVuSans", 8.5)
    pdf.setFillColor(SLATE_500)
    pdf.drawString(
        LEFT_MARGIN,
        note_y,
        _("Tento report obsahuje souhrn vybrané tratě a tři trendové grafy z premium statistik."),
    )


def _draw_detail_page(pdf, rider, track, track_stats):
    pdf.showPage()
    _start_page(
        pdf,
        report_title=_("Premium Statistics Report"),
        page_title=_("Detailní KPI a profil jezdce"),
        section_label="",
    )

    info_y = PAGE_HEIGHT - TOP_MARGIN - 3.0 * cm
    _draw_inline_label(pdf, LEFT_MARGIN, info_y, _("Jezdec"), f"{rider.first_name} {rider.last_name}")
    _draw_inline_label(pdf, LEFT_MARGIN + 7.0 * cm, info_y, _("Trať"), _get_track_name(track))
    _draw_inline_label(pdf, LEFT_MARGIN + 15.2 * cm, info_y, _("Disciplína"), f'{track_stats.get("wheel") or "-"}"')

    box_gap = 0.45 * cm
    box_width = (PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN - box_gap) / 2
    box_height = 4.8 * cm
    top_y = PAGE_HEIGHT - TOP_MARGIN - 3.8 * cm

    for index, (title, items) in enumerate(DETAIL_SECTIONS):
        row = index // 2
        col = index % 2
        x = LEFT_MARGIN + col * (box_width + box_gap)
        y = top_y - row * (box_height + box_gap)
        _draw_metric_list_box(pdf, x, y, box_width, box_height, title, items, track_stats)

    _draw_recent_results_table(pdf, LEFT_MARGIN, 1.55 * cm, PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN, 3.1 * cm, track_stats.get("recent_results") or [])


def _draw_event_tables_page(pdf, rider, track, track_stats):
    table_specs = [
        (_("Finish time podle závodu"), track_stats.get("event_rows") or [], _("Medián dne"), "finish"),
        (_("Hill time podle závodu"), track_stats.get("start_event_rows") or [], _("Medián startu"), "time_only"),
        (_("Split 1 podle závodu"), track_stats.get("split_event_rows") or [], _("Medián Inter2"), "time_only"),
    ]
    rows_per_page = 18
    full_width = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN

    for title, rows, day_median_label, value_type in table_specs:
        row_chunks = list(_chunked(rows, rows_per_page)) or [[]]
        for index, row_chunk in enumerate(row_chunks, start=1):
            pdf.showPage()
            page_title = title
            if len(row_chunks) > 1:
                page_title = _("%(title)s (%(page)s)") % {"title": title, "page": index}
            _start_page(
                pdf,
                report_title=_("Premium Statistics Report"),
                page_title=page_title,
                section_label="",
            )

            info_y = PAGE_HEIGHT - TOP_MARGIN - 3.0 * cm
            _draw_inline_label(pdf, LEFT_MARGIN, info_y, _("Jezdec"), f"{rider.first_name} {rider.last_name}")
            _draw_inline_label(pdf, LEFT_MARGIN + 7.0 * cm, info_y, _("Trať"), _get_track_name(track))
            _draw_inline_label(pdf, LEFT_MARGIN + 15.2 * cm, info_y, _("Disciplína"), f'{track_stats.get("wheel") or "-"}"')

            _draw_event_rows_table_page(
                pdf,
                x=LEFT_MARGIN,
                top_y=PAGE_HEIGHT - TOP_MARGIN - 3.7 * cm,
                width=full_width,
                height=PAGE_HEIGHT - BOTTOM_MARGIN - 4.9 * cm,
                title=title,
                rows=row_chunk,
                day_median_label=day_median_label,
                value_type=value_type,
            )


def _draw_chart_page(pdf, *, rider, track, wheel, page_title, section_label, points, y_ticks, min_time, max_time, line_color, empty_message):
    pdf.showPage()
    _start_page(
        pdf,
        report_title=_("Premium Statistics Report"),
        page_title=page_title,
        section_label="",
    )

    info_y = PAGE_HEIGHT - TOP_MARGIN - 3.0 * cm
    _draw_inline_label(pdf, LEFT_MARGIN, info_y, _("Jezdec"), f"{rider.first_name} {rider.last_name}")
    _draw_inline_label(pdf, LEFT_MARGIN + 7.0 * cm, info_y, _("Trať"), _get_track_name(track))
    _draw_inline_label(pdf, LEFT_MARGIN + 15.2 * cm, info_y, _("Disciplína"), f'{wheel or "-"}"')

    if points:
        range_text = _("Rozsah %(min)s s až %(max)s s") % {
            "min": _format_value(min_time, digits=3).replace(" s", ""),
            "max": _format_value(max_time, digits=3).replace(" s", ""),
        }
        pdf.setFont("DejaVuSans", 9)
        pdf.setFillColor(SLATE_500)
        pdf.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, info_y, range_text)

    chart_y = 3.2 * cm
    chart_height = PAGE_HEIGHT - chart_y - TOP_MARGIN - 4.6 * cm
    _draw_chart_box(
        pdf,
        x=LEFT_MARGIN,
        y=chart_y,
        width=PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN,
        height=chart_height,
        points=points,
        y_ticks=y_ticks,
        line_color=line_color,
        empty_message=empty_message,
    )


def _start_page(pdf, *, report_title, page_title, section_label):
    pdf.setFillColor(WHITE)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)

    header_bottom = PAGE_HEIGHT - TOP_MARGIN - 2.2 * cm
    pdf.setStrokeColor(SLATE_200)
    pdf.line(LEFT_MARGIN, header_bottom, PAGE_WIDTH - RIGHT_MARGIN, header_bottom)

    logo = _get_logo_reader()
    if logo is not None:
        pdf.drawImage(
            logo,
            PAGE_WIDTH - RIGHT_MARGIN - 1.95 * cm,
            PAGE_HEIGHT - TOP_MARGIN - 0.55 * cm,
            width=1.35 * cm,
            height=0.9 * cm,
            preserveAspectRatio=True,
            mask="auto",
        )

    pdf.setFillColor(SLATE_500)
    pdf.setFont("DejaVuSans", 9)
    pdf.drawString(LEFT_MARGIN, PAGE_HEIGHT - TOP_MARGIN + 0.1 * cm, report_title)

    pdf.setFillColor(SLATE_900)
    pdf.setFont("DejaVuSans-Bold", 19)
    pdf.drawString(LEFT_MARGIN, PAGE_HEIGHT - TOP_MARGIN - 0.95 * cm, page_title)

    if section_label:
        pdf.setFillColor(INDIGO)
        pdf.setFont("DejaVuSans-Bold", 8)
        pdf.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, PAGE_HEIGHT - TOP_MARGIN + 0.1 * cm, section_label.upper())

    footer_y = BOTTOM_MARGIN - 0.05 * cm
    pdf.setStrokeColor(SLATE_200)
    pdf.line(LEFT_MARGIN, footer_y + 0.22 * cm, PAGE_WIDTH - RIGHT_MARGIN, footer_y + 0.22 * cm)
    pdf.setFillColor(SLATE_500)
    pdf.setFont("DejaVuSans", 8)
    pdf.drawString(LEFT_MARGIN, footer_y, _("Premium statistics report"))
    pdf.setFillColor(SLATE_300)
    pdf.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, footer_y, timezone.localtime().strftime("%d.%m.%Y %H:%M"))


def _draw_info_box(pdf, x, top_y, width, title, lines):
    height = 3.4 * cm
    y = top_y - height
    pdf.setFillColor(SLATE_100)
    pdf.setStrokeColor(SLATE_200)
    pdf.roundRect(x, y, width, height, 10, stroke=1, fill=1)

    pdf.setFillColor(SLATE_700)
    pdf.setFont("DejaVuSans-Bold", 10)
    pdf.drawString(x + 0.35 * cm, top_y - 0.65 * cm, title)

    pdf.setFillColor(SLATE_900)
    pdf.setFont("DejaVuSans", 10)
    current_y = top_y - 1.35 * cm
    for line in lines:
        pdf.drawString(x + 0.35 * cm, current_y, line)
        current_y -= 0.58 * cm


def _draw_stat_card(pdf, x, top_y, width, height, label, value):
    y = top_y - height
    pdf.setFillColor(WHITE)
    pdf.setStrokeColor(SLATE_200)
    pdf.roundRect(x, y, width, height, 9, stroke=1, fill=1)

    pdf.setFillColor(SLATE_500)
    pdf.setFont("DejaVuSans-Bold", 8)
    pdf.drawString(x + 0.28 * cm, top_y - 0.55 * cm, label.upper())

    pdf.setFillColor(SLATE_900)
    pdf.setFont("DejaVuSans-Bold", 17)
    pdf.drawString(x + 0.28 * cm, y + 0.72 * cm, value)


def _draw_inline_label(pdf, x, y, label, value):
    pdf.setFillColor(SLATE_500)
    pdf.setFont("DejaVuSans-Bold", 8)
    pdf.drawString(x, y, f"{label.upper()}:")
    pdf.setFillColor(SLATE_900)
    pdf.setFont("DejaVuSans", 9)
    offset = max(2.2 * cm, pdf.stringWidth(f"{label.upper()}:", "DejaVuSans-Bold", 8) + 0.18 * cm)
    pdf.drawString(x + offset, y, value)


def _render_metric_value(value, *, digits=2, suffix=""):
    if value in (None, ""):
        return "-"
    if digits is None:
        return str(value)
    return _format_value(value, digits=digits, suffix=suffix)


def _get_track_name(track):
    if isinstance(track, dict):
        return track.get("name") or "-"
    return getattr(track, "name", "-") or "-"


def _split_text_to_width(pdf, text, font_name, font_size, max_width):
    words = str(text).split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _ellipsize_to_width(pdf, text, font_name, font_size, max_width):
    text = str(text)
    if pdf.stringWidth(text, font_name, font_size) <= max_width:
        return text
    ellipsis = "..."
    trimmed = text
    while trimmed and pdf.stringWidth(trimmed + ellipsis, font_name, font_size) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ellipsis) if trimmed else ellipsis


def _fit_text_lines(pdf, text, font_name, font_size, max_width, max_lines=2):
    wrapped = _split_text_to_width(pdf, text, font_name, font_size, max_width)
    if len(wrapped) <= max_lines:
        return wrapped
    fitted = wrapped[: max_lines - 1]
    remainder = " ".join(wrapped[max_lines - 1 :])
    fitted.append(_ellipsize_to_width(pdf, remainder, font_name, font_size, max_width))
    return fitted


def _draw_metric_list_box(pdf, x, top_y, width, height, title, items, track_stats):
    y = top_y - height
    pdf.setFillColor(SLATE_100)
    pdf.setStrokeColor(SLATE_200)
    pdf.roundRect(x, y, width, height, 9, stroke=1, fill=1)

    pdf.setFillColor(SLATE_700)
    pdf.setFont("DejaVuSans-Bold", 10)
    pdf.drawString(x + 0.3 * cm, top_y - 0.55 * cm, title)

    current_y = top_y - 1.05 * cm
    label_width = width * 0.44
    value_width = width * 0.30
    for key, label, digits, suffix in items:
        pdf.setFillColor(SLATE_500)
        pdf.setFont("DejaVuSans", 7.2)
        label_lines = _fit_text_lines(pdf, f"{label}:", "DejaVuSans", 7.2, label_width, max_lines=2)
        for offset, line in enumerate(label_lines):
            pdf.drawString(x + 0.26 * cm, current_y - offset * 0.24 * cm, line)
        pdf.setFillColor(SLATE_900)
        pdf.setFont("DejaVuSans-Bold", 7.0)
        value = _render_metric_value(track_stats.get(key), digits=digits, suffix=suffix)
        value_lines = _fit_text_lines(pdf, value, "DejaVuSans-Bold", 7.0, value_width, max_lines=2)
        value_x = x + width - 0.26 * cm - value_width
        for offset, line in enumerate(value_lines):
            pdf.drawString(value_x, current_y - offset * 0.24 * cm, line)
        current_y -= max(len(label_lines), len(value_lines)) * 0.24 * cm + 0.10 * cm


def _draw_recent_results_table(pdf, x, y, width, height, recent_results):
    pdf.setFillColor(WHITE)
    pdf.setStrokeColor(SLATE_200)
    pdf.roundRect(x, y, width, height, 9, stroke=1, fill=1)

    pdf.setFillColor(SLATE_700)
    pdf.setFont("DejaVuSans-Bold", 10)
    pdf.drawString(x + 0.3 * cm, y + height - 0.5 * cm, _("Poslední výsledky"))

    headers = [_("Datum"), _("Závod"), _("Place"), _("Kategorie")]
    col_positions = [x + 0.3 * cm, x + 3.0 * cm, x + width - 3.4 * cm, x + width - 1.0 * cm]
    header_y = y + height - 1.05 * cm

    pdf.setFillColor(SLATE_500)
    pdf.setFont("DejaVuSans-Bold", 8)
    for index, header in enumerate(headers):
        align_right = index >= 2
        if align_right:
            pdf.drawRightString(col_positions[index], header_y, header)
        else:
            pdf.drawString(col_positions[index], header_y, header)

    row_y = header_y - 0.45 * cm
    max_rows = 4
    pdf.setFont("DejaVuSans", 8)
    for result in recent_results[:max_rows]:
        pdf.setFillColor(SLATE_900)
        pdf.drawString(col_positions[0], row_y, result.date.strftime("%d.%m.%Y") if getattr(result, "date", None) else "-")
        event_name = getattr(getattr(result, "event", None), "name", None) or "-"
        trimmed_name = event_name[:42] + "..." if len(event_name) > 45 else event_name
        pdf.drawString(col_positions[1], row_y, trimmed_name)
        pdf.drawRightString(col_positions[2], row_y, str(result.place or "-"))
        pdf.drawRightString(col_positions[3], row_y, str(result.category or "-"))
        pdf.setStrokeColor(SLATE_200)
        pdf.line(x + 0.25 * cm, row_y - 0.14 * cm, x + width - 0.25 * cm, row_y - 0.14 * cm)
        row_y -= 0.45 * cm


def _draw_event_rows_table_page(pdf, *, x, top_y, width, height, title, rows, day_median_label, value_type):
    y = top_y - height
    pdf.setFillColor(WHITE)
    pdf.setStrokeColor(SLATE_200)
    pdf.roundRect(x, y, width, height, 9, stroke=1, fill=1)

    pdf.setFillColor(SLATE_700)
    pdf.setFont("DejaVuSans-Bold", 10)
    pdf.drawString(x + 0.3 * cm, top_y - 0.5 * cm, title)

    headers = [_("Datum"), _("Závod"), day_median_label]
    col_x = [x + 0.3 * cm, x + 2.6 * cm, x + width - 0.3 * cm]
    header_y = top_y - 1.0 * cm

    pdf.setFillColor(SLATE_500)
    pdf.setFont("DejaVuSans-Bold", 8)
    pdf.drawString(col_x[0], header_y, headers[0])
    pdf.drawString(col_x[1], header_y, headers[1])
    pdf.drawRightString(col_x[2], header_y, headers[2])

    current_y = header_y - 0.42 * cm
    pdf.setFont("DejaVuSans", 7.8)
    for row in rows:
        pdf.setFillColor(SLATE_900)
        row_date = row.get("date")
        pdf.drawString(col_x[0], current_y, row_date.strftime("%d.%m.%Y") if row_date else "-")
        event_name = row.get("event_name") or "-"
        trimmed_name = event_name[:46] + "..." if len(event_name) > 49 else event_name
        pdf.drawString(col_x[1], current_y, trimmed_name)
        pdf.drawRightString(col_x[2], current_y, _extract_day_median(row.get("cells") or [], value_type))
        pdf.setStrokeColor(SLATE_200)
        pdf.line(x + 0.25 * cm, current_y - 0.13 * cm, x + width - 0.25 * cm, current_y - 0.13 * cm)
        current_y -= 0.45 * cm

    if not rows:
        pdf.setFillColor(SLATE_500)
        pdf.setFont("DejaVuSans", 9)
        pdf.drawCentredString(x + width / 2, y + height / 2, _("Pro tuto tabulku zatím nejsou dostupná data."))


def _chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _extract_day_median(cells, value_type):
    for cell in cells:
        if cell.get("key") != "DAY_MEDIAN" or not cell.get("value"):
            continue
        value = cell["value"]
        if value_type == "finish":
            place = value.get("place") or ""
            time = value.get("time")
            if place and time is not None:
                return f"{place} / {_format_value(time, digits=3, suffix=' s')}"
            if time is not None:
                return _format_value(time, digits=3, suffix=" s")
        else:
            time = value.get("time")
            if time is not None:
                return _format_value(time, digits=3, suffix=" s")
    return "-"


def _draw_chart_box(pdf, *, x, y, width, height, points, y_ticks, line_color, empty_message):
    pdf.setFillColor(WHITE)
    pdf.setStrokeColor(SLATE_200)
    pdf.roundRect(x, y, width, height, 10, stroke=1, fill=1)

    if not points:
        pdf.setFillColor(SLATE_500)
        pdf.setFont("DejaVuSans", 11)
        pdf.drawCentredString(x + width / 2, y + height / 2, empty_message)
        return

    source_left = 56
    source_right = 976
    source_bottom = 216
    source_top = 24

    plot_x = x + 1.4 * cm
    plot_y = y + 1.6 * cm
    plot_width = width - 2.3 * cm
    plot_height = height - 3.0 * cm

    def map_x(source_x):
        return plot_x + ((source_x - source_left) / (source_right - source_left)) * plot_width

    def map_y(source_y):
        return plot_y + ((source_bottom - source_y) / (source_bottom - source_top)) * plot_height

    pdf.setStrokeColor(SLATE_300)
    pdf.setLineWidth(0.8)
    pdf.line(plot_x, plot_y, plot_x + plot_width, plot_y)
    pdf.line(plot_x, plot_y, plot_x, plot_y + plot_height)

    pdf.setFont("DejaVuSans", 8)
    for tick in y_ticks:
        tick_y = map_y(tick["y"])
        pdf.setStrokeColor(SLATE_200)
        pdf.line(plot_x, tick_y, plot_x + plot_width, tick_y)
        pdf.setFillColor(SLATE_500)
        pdf.drawRightString(plot_x - 0.15 * cm, tick_y - 2, str(tick["label"]).replace(".", ","))

    pdf.setStrokeColor(line_color)
    pdf.setLineWidth(2)
    for first, second in zip(points, points[1:]):
        pdf.line(map_x(first["x"]), map_y(first["y"]), map_x(second["x"]), map_y(second["y"]))

    for point in points:
        px = map_x(point["x"])
        py = map_y(point["y"])
        pdf.setFillColor(line_color)
        pdf.circle(px, py, 3, stroke=0, fill=1)
        pdf.setFillColor(SLATE_500)
        pdf.setFont("DejaVuSans", 7.5)
        pdf.drawCentredString(px, plot_y - 0.45 * cm, point.get("short_label", ""))

    pdf.setFillColor(SLATE_500)
    pdf.setFont("DejaVuSans", 8)
    pdf.drawRightString(plot_x + plot_width, y + 0.5 * cm, _("Datum závodu"))
