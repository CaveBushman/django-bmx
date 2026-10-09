import logging

logger = logging.getLogger(__name__)
from django.shortcuts import render
from rider.trainer_dashboard import (
    build_club_kpi_export_rows,
    build_club_riders_export_rows,
    build_trainer_dashboard_context,
    build_trainer_export_filename,
    export_rows_as_csv,
    export_rows_as_xlsx,
    get_exportable_trainer_club_or_403,
    normalize_export_format_or_404,
    handle_trainer_dashboard_post,
)


from rider.views._common import *  # noqa: F401,F403


@trainer_dashboard_required
def trainer_dashboard_view(request):
    if request.method == "POST":
        post_response = handle_trainer_dashboard_post(request)
        if post_response is not None:
            return post_response

    context = build_trainer_dashboard_context(request.user)
    return render(request, "rider/trainer-dashboard.html", context)



@trainer_dashboard_required
def trainer_club_riders_export_view(request, club_id, export_format):
    export_format = normalize_export_format_or_404(export_format)
    club = get_exportable_trainer_club_or_403(request.user, club_id)
    rows = build_club_riders_export_rows(club)
    headers = [
        ("uci_id", "UCI ID"),
        ("first_name", "Jméno"),
        ("last_name", "Příjmení"),
        ("class_20", "Kategorie 20\""),
        ("class_24", "Kategorie 24\""),
        ("plate", "Číslo"),
        ("transponder_20", "Transpondér 20\""),
        ("transponder_24", "Transpondér 24\""),
        ("valid_licence", "Platná licence"),
        ("email", "E-mail"),
        ("phone", "Telefon"),
    ]
    filename = build_trainer_export_filename(club, "riders")
    if export_format == "xlsx":
        return export_rows_as_xlsx(f"{filename}.xlsx", "Riders", headers, rows)
    return export_rows_as_csv(f"{filename}.csv", headers, rows)



@trainer_dashboard_required
def trainer_club_kpi_export_view(request, club_id, export_format):
    export_format = normalize_export_format_or_404(export_format)
    club = get_exportable_trainer_club_or_403(request.user, club_id)
    rows = build_club_kpi_export_rows(club)
    headers = [
        ("uci_id", "UCI ID"),
        ("first_name", "Jméno"),
        ("last_name", "Příjmení"),
        ("class_20", "Kategorie 20\""),
        ("class_24", "Kategorie 24\""),
        ("starts_total", "Starty celkem"),
        ("starts_last_2y", "Starty za 2 roky"),
        ("best_result", "Best result"),
        ("avg_place", "Průměrné pořadí"),
        ("median_finish", "Medián finish"),
        ("best_finish", "Best finish"),
        ("median_hill", "Medián hill"),
        ("median_split_1", "Medián split 1"),
    ]
    filename = build_trainer_export_filename(club, "kpi")
    if export_format == "xlsx":
        return export_rows_as_xlsx(f"{filename}.xlsx", "KPI", headers, rows)
    return export_rows_as_csv(f"{filename}.csv", headers, rows)


__all__ = [
    'trainer_dashboard_view',
    'trainer_club_riders_export_view',
    'trainer_club_kpi_export_view',
]
