"""
event/views/views_admin.py — admin a komisařské operace

Obsah:
  Veřejné view funkce (URL handlery):
    - event_admin_view       — hlavní admin panel závodu
    - ec_by_club_xls         — export přihlášek EP po klubech
    - summary_riders_in_event — počty jezdců v kategoriích
    - export_event_results   — odeslání výsledků do API ČSC
    - send_invoices          — TODO
    - price_money_pdf        — TODO

  Privátní helpery pro event_admin_view (prefix _handle_):
    - _handle_ec_event       — Evropský pohár / Mistrovství Evropy
    - _handle_upload_xls     — nahrání BEM XLS výsledků
    - _handle_delete_xls     — smazání BEM XLS výsledků
    - _handle_bem_entries    — generování BEM startovky (přihlášení jezdci)
    - _handle_bem_riders     — generování BEM seznamu všech jezdců
    - _handle_rem_entries    — generování REM online přihlášek
    - _handle_upload_txt     — nahrání REM TSV výsledků + RaceRun záznamy
    - _handle_delete_txt     — smazání REM výsledků
    - _write_bem_rider_row   — pomocný zápis jednoho jezdce do BEM XLS řádku
"""

import logging
import json
import datetime
import os
from collections import Counter
from io import BytesIO
import requests
import pikepdf
from datetime import date
from types import SimpleNamespace
from django.shortcuts import get_object_or_404, render, reverse, HttpResponseRedirect, redirect
from django.http import FileResponse, HttpResponse
from django.contrib import messages
from django.core.files.base import ContentFile
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.db.models import Count, Q
from django.template.defaultfilters import slugify
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.cache import cache_control
from django.utils.translation import gettext as _
from event.models import Event, Entry, EntryForeign, Result, RaceRun
from club.models import Club, McrClubTeam, McrClubTeamMember
from commissar.models import Commissar
from rider.models import Rider
from event.func import (
    invalid_licence_in_event,
    excel_first_line, expire_licence, gender_resolve,
    gender_resolve_small_letter, team_name_resolve, resolve_event_classes,
    foreign_club_resolve,
    SetResults,
)
from event.entry import REMRiders
from event.result import GetResult
from ranking.ranking import schedule_ranking_recount
from rider.rider import (
    get_api_token,
    generate_insurance_file,
    resolve_api_category_code,
    trigger_cn_qualification_recount_if_needed,
)
from finance.invoices import generate_event_invoices, send_event_invoices
from event.prize_money import PrizeMoneyPdfService
from event.services.race_run_import import RaceRunImportService, START_KEYS, RESULT_KEYS
from event.services.uci_export import (
    generate_uci_export_zip,
    get_missing_uci_competition_codes,
)
from event.services.unpaid_moto_report import build_unpaid_moto_report
from event.services.unpaid_moto_report_pdf import UnpaidMotoReportPdfService
from accounts.push_notifications import send_to_users
from openpyxl import Workbook, load_workbook
import pandas as pd
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")
MAX_RESULTS_PDF_SIZE_BYTES = 20 * 1024 * 1024
CCF_API_TIMEOUT = (5, 20)

COMMISSAR_EXCLUDED_EVENT_TYPES = [
    "Evropský pohár",
    "Mistrovství Evropy",
    "Mistrovství světa",
    "Světový pohár",
]

COMMISSAR_PLACEHOLDER_LAST_NAME = "Bude upřesněno"

UCI_EXPORT_TEMPLATE = os.path.join(settings.MEDIA_ROOT, "uci-templates", "uci-results-template.xlsx")


def _render_error_page(request, message, *, detail=None, status=400):
    context = {"message": message}
    if detail:
        context["detail"] = detail
    return render(request, "error.html", context, status=status)


def _get_event_year_options():
    return (
        Event.objects.exclude(date__isnull=True)
        .dates("date", "year", order="DESC")
    )


def _resolve_selected_year(selected_year, year_options):
    if selected_year is None:
        return str(year_options[0].year) if year_options else str(date.today().year)
    if not selected_year.isdigit():
        return str(year_options[0].year) if year_options else str(date.today().year)
    return selected_year


def _is_mcr_club_teams_event(event):
    return event.type_for_ranking == "Mistrovství ČR družstev"


def _get_mcr_club_teams_year(event):
    return event.date.year if event.date else date.today().year


def _get_mcr_club_teams_for_event(event):
    return (
        McrClubTeam.objects.filter(year=_get_mcr_club_teams_year(event))
        .select_related("club")
        .prefetch_related("members__rider")
        .order_by("club__team_name", "name")
    )


def _get_mcr_club_teams_riders_count(event):
    return (
        McrClubTeamMember.objects.filter(team__year=_get_mcr_club_teams_year(event))
        .values("rider_id")
        .distinct()
        .count()
    )


def can_access_commissar_pages(user):
    return user.is_authenticated and (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or getattr(user, "is_commission", False)
    )


def can_edit_commissar_assignments(user):
    return user.is_authenticated and (
        getattr(user, "is_superuser", False)
        or getattr(user, "is_commission", False)
    )


commissar_pages_required = user_passes_test(
    can_access_commissar_pages,
    login_url="/bmx-admin/login/",
)


def _build_media_storage(*parts):
    relative_dir = os.path.join(*parts)
    return FileSystemStorage(
        location=os.path.join(settings.MEDIA_ROOT, relative_dir),
        base_url=f"{settings.MEDIA_URL}{relative_dir}/",
    ), relative_dir


def _save_uploaded_file(uploaded_file, *storage_parts):
    storage, relative_dir = _build_media_storage(*storage_parts)
    if storage.exists(uploaded_file.name):
        storage.delete(uploaded_file.name)
    filename = storage.save(uploaded_file.name, uploaded_file)
    return storage, filename, os.path.join(relative_dir, filename)


def _merge_uploaded_pdfs(*uploaded_files):
    merged_buffer = BytesIO()
    appended_any_file = False

    with pikepdf.Pdf.new() as merged_pdf:
        for uploaded_file in uploaded_files:
            if not uploaded_file:
                continue
            uploaded_file.seek(0)
            with pikepdf.Pdf.open(BytesIO(uploaded_file.read())) as source_pdf:
                merged_pdf.pages.extend(source_pdf.pages)
                appended_any_file = True

        if not appended_any_file:
            raise ValueError("Nebyl nahrán žádný PDF soubor.")

        merged_pdf.save(merged_buffer)

    return merged_buffer.getvalue()


def _validate_uploaded_results_pdf(uploaded_file, field_label, required=False):
    if not uploaded_file:
        if required:
            raise ValueError(f"Nahraj {field_label}.")
        return

    filename = (uploaded_file.name or "").lower()
    if not filename.endswith(".pdf"):
        raise ValueError(f"{field_label} musí být PDF soubor.")

    content_type = (uploaded_file.content_type or "").lower()
    if content_type and content_type not in {"application/pdf", "application/x-pdf"}:
        raise ValueError(f"{field_label} nemá platný PDF content type.")

    if uploaded_file.size > MAX_RESULTS_PDF_SIZE_BYTES:
        raise ValueError(
            f"{field_label} je příliš velké. Maximální velikost je {MAX_RESULTS_PDF_SIZE_BYTES // (1024 * 1024)} MB."
        )


def _build_ec_results_pdf_name(event):
    event_slug = slugify(event.name) or f"event-{event.id}"
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"ec-results-{event.id}-{event_slug}-{timestamp}.pdf"


def _handle_ec_results_pdf_upload(request, event):
    uploaded_pdfs = [uploaded_file for uploaded_file in request.FILES.getlist("results-pdf-files") if uploaded_file]

    if not uploaded_pdfs:
        messages.error(request, "Nahraj alespoň jeden PDF soubor s výsledky.")
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": event.id}))

    try:
        for index, uploaded_pdf in enumerate(uploaded_pdfs, start=1):
            _validate_uploaded_results_pdf(uploaded_pdf, f"PDF s výsledky #{index}", required=True)
        merged_pdf_bytes = _merge_uploaded_pdfs(*uploaded_pdfs)
    except Exception as exc:
        logger.exception("Chyba při spojování PDF výsledků pro event_id=%s", event.id)
        messages.error(request, f"Nepodařilo se spojit PDF soubory: {exc}")
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": event.id}))

    event.full_results.save(
        _build_ec_results_pdf_name(event),
        ContentFile(merged_pdf_bytes),
        save=False,
    )
    event.save(update_fields=["full_results"])

    messages.success(request, "Výsledky byly nahrány a zveřejněny jako jedno sloučené PDF.")
    audit_logger.info(
        "event_ec_results_pdf_uploaded admin_user_id=%s event_id=%s pdf_count=%s",
        request.user.id,
        event.id,
        len(uploaded_pdfs),
    )
    return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": event.id}))


def _handle_ec_results_pdf_delete(request, event):
    if event.full_results:
        event.full_results.delete(save=True)
        messages.success(request, "Zveřejněné PDF výsledků bylo smazáno.")
        audit_logger.info(
            "event_ec_results_pdf_deleted admin_user_id=%s event_id=%s",
            request.user.id,
            event.id,
        )
    else:
        messages.warning(request, "U závodu není nahrané žádné zveřejněné PDF výsledků.")
    return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": event.id}))


def _generate_ec_file(event):
    entries = Entry.objects.filter(
        event=event.id,
        payment_complete=True,
        checkout=False,
    ).select_related("rider")

    template = os.path.join(
        settings.MEDIA_ROOT,
        "ec-files",
        "Entries example - UEC.xlsx"
        if event.type_for_ranking == "Evropský pohár"
        else "Entries_upload_UEC_Champ_2024.xlsx",
    )
    target_path = os.path.join(
        settings.MEDIA_ROOT,
        "ec-files",
        f"EC_RACE_ID-{event.id}-{event.name}.xlsx",
    )
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    wb = load_workbook(filename=template)
    ws = wb.active

    row_index = 3
    for entry in entries:
        rider = entry.rider
        try:
            ws.cell(row_index, 2, rider.uci_id)
            ws.cell(row_index, 3, rider.date_of_birth)
            ws.cell(row_index, 4, rider.first_name)
            ws.cell(row_index, 5, rider.last_name)
            ws.cell(row_index, 6, gender_resolve_small_letter(rider.gender))
            ws.cell(row_index, 7, rider.transponder_20 if entry.is_20 else rider.transponder_24)
            if entry.is_24:
                ws.cell(row_index, 8, "x")
            if entry.is_20:
                if rider.is_elite:
                    ws.cell(row_index, 9, "x")
                if rider.class_20 in ["Women Under 23", "Men Under 23"]:
                    ws.cell(row_index, 10, "x")
            row_index += 1
        except Exception as exc:
            logger.error("Chyba při zápisu do EC souboru pro event_id=%s rider_id=%s: %s", event.id, rider.uci_id, exc)

    wb.save(target_path)
    event.ec_file = target_path
    event.ec_file_created = timezone.now()
    event.save(update_fields=["ec_file", "ec_file_created"])
    return target_path


def _get_ec_admin_context(event):
    entries = Entry.objects.filter(
        event=event.id,
        payment_complete=True,
        checkout=False,
    )
    payments = sum((entry.fee_20 if entry.is_20 else 0) + (entry.fee_24 if entry.is_24 else 0) for entry in entries)
    sum_entries = entries.filter(Q(is_20=True) | Q(is_24=True)).count()
    return {
        "event": event,
        "sum_entries": sum_entries,
        "payments": payments,
    }


def _delete_uploaded_files_by_prefix(*storage_parts, prefix):
    storage, _ = _build_media_storage(*storage_parts)
    location = getattr(storage, "location", "")
    if not location or not os.path.isdir(location):
        return 0

    deleted_count = 0
    filename_prefix = f"{prefix}__"
    for existing_name in os.listdir(location):
        existing_path = os.path.join(location, existing_name)
        if not os.path.isfile(existing_path):
            continue
        if not existing_name.startswith(filename_prefix):
            continue
        storage.delete(existing_name)
        deleted_count += 1
    return deleted_count


def _download_generated_file(file_path):
    file_handle = open(file_path, "rb")
    return FileResponse(file_handle, as_attachment=True, filename=os.path.basename(file_path))


def _save_workbook_to_project_path(workbook, relative_file_name):
    file_path = os.path.join(settings.BASE_DIR, relative_file_name)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    workbook.save(file_path)
    return file_path


def _resolve_association_fee(sum_of_fees, commission_fee):
    try:
        normalized_fee = int(commission_fee or 0)
    except (TypeError, ValueError):
        logger.warning("Neplatná commission_fee=%r při výpočtu asociační odměny.", commission_fee)
        normalized_fee = 0
    return int(sum_of_fees * normalized_fee / 100)


# ===========================================================================
# PRIVÁTNÍ HELPERY — volány z event_admin_view
# Každý helper zpracuje jeden btn-* blok a vrátí response nebo None.
# None = pokračuj dál (zobraz shrnutí), response = okamžitý redirect/render.
# ===========================================================================

def _handle_ec_event(request, event):
    """Admin stránka pro Evropský pohár / ME s explicitními akcemi."""
    if request.method == "POST":
        if "btn-upload-ec-results-pdf" in request.POST:
            return _handle_ec_results_pdf_upload(request, event)
        if "btn-delete-ec-results-pdf" in request.POST:
            return _handle_ec_results_pdf_delete(request, event)
        if "btn-generate-ec-file" in request.POST:
            try:
                file_path = _generate_ec_file(event)
                audit_logger.info(
                    "event_ec_file_generated_and_downloaded admin_user_id=%s event_id=%s",
                    request.user.id,
                    event.id,
                )
                return _download_generated_file(file_path)
            except Exception as exc:
                logger.exception("Chyba při generování UEC XLS pro event_id=%s", event.id)
                messages.error(request, f"Nepodařilo se vygenerovat UEC XLS: {exc}")
            return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": event.id}))
        if "btn-generate-ec-insurance-file" in request.POST:
            try:
                file_path = generate_insurance_file(event)
                audit_logger.info(
                    "event_ec_insurance_file_generated_and_downloaded admin_user_id=%s event_id=%s",
                    request.user.id,
                    event.id,
                )
                return _download_generated_file(file_path)
            except Exception as exc:
                logger.exception("Chyba při generování pojišťovacího XLS pro event_id=%s", event.id)
                messages.error(request, f"Nepodařilo se vygenerovat XLS pro pojišťovnu: {exc}")
            return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": event.id}))

    return render(request, "event/event-admin-ec.html", _get_ec_admin_context(event))


def _handle_upload_xls(request, event, pk):
    """Nahraje XLS výsledky z BEM a přepočítá ranking."""
    if "result-file" not in request.FILES:
        messages.error(request, "Musíš vybrat soubor s výsledky závodu")
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": pk}))

    result_file = request.FILES["result-file"]
    storage, filename, relative_path = _save_uploaded_file(result_file, "xls_results")

    ranking_code = GetResult.ranking_code_resolve(type=event.type_for_ranking)
    data = pd.read_excel(storage.path(filename), sheet_name="Results")

    for i in range(1, len(data.index)):
        GetResult(
            event.date, event.id, event.name, ranking_code,
            str(data.iloc[i][1]), str(data.iloc[i][0]), data.iloc[i][5],
            data.iloc[i][2], data.iloc[i][3], data.iloc[i][6],
            event.organizer.team_name, event.type_for_ranking,
        ).write_result()

    event.xls_results = relative_path
    event.save()
    schedule_ranking_recount()
    trigger_cn_qualification_recount_if_needed(event)
    logger.info(f"BEM výsledky nahrány pro závod {event.id}")
    audit_logger.info(
        "event_bem_results_uploaded admin_user_id=%s event_id=%s filename=%s",
        request.user.id,
        event.id,
        filename,
    )
    return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": pk}))


def _handle_delete_xls(request, event, pk):
    """Smaže XLS výsledky a přepočítá ranking."""
    Result.objects.filter(event=pk).delete()
    schedule_ranking_recount()
    try:
        xls_path = event.xls_results.path
    except (ValueError, NotImplementedError):
        xls_path = None
    if xls_path:
        try:
            os.remove(xls_path)
        except FileNotFoundError:
            logger.warning(f"XLS soubor nenalezen při mazání: {xls_path}")
    event.xls_results.delete(save=True)
    logger.info(f"BEM výsledky smazány pro závod {event.id}")
    audit_logger.info(
        "event_bem_results_deleted admin_user_id=%s event_id=%s",
        request.user.id,
        event.id,
    )
    return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": pk}))


def _write_bem_rider_row(ws, row, rider, event, is_20):
    """Zapíše data jednoho jezdce do zadaného řádku BEM XLS souboru.

    Sdílený kód pro startovku (přihlášení jezdci) i seznam všech jezdců.
    """
    ws.cell(row, 1, rider.uci_id)
    ws.cell(row, 2, rider.uci_id)
    ws.cell(row, 3, rider.uci_id)
    ws.cell(row, 4, rider.uci_id)
    ws.cell(row, 5, rider.uci_id)
    ws.cell(row, 6, expire_licence())
    ws.cell(row, 7, "BMX-RACE")
    ws.cell(row, 9, str(rider.date_of_birth).replace("-", "/"))
    ws.cell(row, 10, rider.first_name)
    ws.cell(row, 11, rider.last_name.upper())
    ws.cell(row, 12, rider.email)
    ws.cell(row, 13, rider.phone)
    ws.cell(row, 14, rider.emergency_contact)
    ws.cell(row, 15, rider.emergency_phone)
    ws.cell(row, 16, gender_resolve(rider))
    ws.cell(row, 17, team_name_resolve(rider.club))
    ws.cell(row, 18, "CZE")
    ws.cell(row, 19, "CZE")

    if is_20:
        ws.cell(row, 20, resolve_event_classes(event, rider, is_20=True))
        world_plate = ("W" + str(rider.plate_champ_20)) if rider.plate_champ_20 else rider.plate_display
        ws.cell(row, 24, world_plate)
        ws.cell(row, 25, rider.plate_display)
    else:
        ws.cell(row, 21, resolve_event_classes(event, rider, is_20=False))
        world_plate = ("W" + str(rider.plate_champ_24)) if rider.plate_champ_24 else rider.plate_display
        ws.cell(row, 24, rider.plate_display)
        ws.cell(row, 25, world_plate)

    ws.cell(row, 32, rider.transponder_20)
    ws.cell(row, 33, rider.transponder_24)
    ws.cell(row, 36, "T1")
    ws.cell(row, 37, "T2")
    ws.cell(row, 45, team_name_resolve(rider.club).upper())
    ws.cell(row, 46, "" if rider.valid_licence else "NEPLATNÁ LICENCE")


def _write_bem_foreign_entry_row(ws, row, entry, is_20):
    """Zapíše zahraniční přihlášku do zadaného řádku BEM XLS souboru."""
    ws.cell(row, 1, entry.uci_id)
    ws.cell(row, 2, entry.uci_id)
    ws.cell(row, 3, entry.uci_id)
    ws.cell(row, 4, entry.uci_id)
    ws.cell(row, 5, entry.uci_id)
    ws.cell(row, 6, expire_licence())
    ws.cell(row, 7, "BMX-RACE")
    ws.cell(row, 9, str(entry.date_of_birth).replace("-", "/") if entry.date_of_birth else "")
    ws.cell(row, 10, entry.first_name)
    ws.cell(row, 11, (entry.last_name or "").upper())
    ws.cell(row, 12, entry.customer_email or "")
    ws.cell(row, 13, "")
    ws.cell(row, 14, "")
    ws.cell(row, 15, "")
    ws.cell(row, 16, "F" if entry.gender == "Žena" else "M")

    club_name = entry.club or foreign_club_resolve(entry.nationality or "")
    ws.cell(row, 17, club_name)
    ws.cell(row, 18, entry.nationality or "")
    ws.cell(row, 19, entry.nationality or "")

    if is_20:
        ws.cell(row, 20, entry.class_20 or "")
        ws.cell(row, 24, entry.plate)
        ws.cell(row, 25, entry.plate)
        ws.cell(row, 32, entry.transponder_20)
        ws.cell(row, 33, entry.transponder_24)
    else:
        ws.cell(row, 21, entry.class_24 or "")
        ws.cell(row, 24, entry.plate)
        ws.cell(row, 25, entry.plate)
        ws.cell(row, 32, entry.transponder_20)
        ws.cell(row, 33, entry.transponder_24)

    ws.cell(row, 36, "T1")
    ws.cell(row, 37, "T2")
    ws.cell(row, 45, (club_name or "").upper())
    ws.cell(row, 46, "")


def _handle_bem_entries(request, event):
    """Vygeneruje BEM startovku (XLS) pro přihlášené jezdce na závod."""
    file_name = f"media/bem-files/BEM_FOR_RACE_ID-{event.id}-{event.name}.xlsx"
    wb = Workbook()
    wb.encoding = "utf-8"
    ws = wb.active
    ws.title = "BEM5_EXT"
    ws = excel_first_line(ws)

    x = 2
    for entry in Entry.objects.filter(event=event.id, is_20=True, payment_complete=True, checkout=False):
        try:
            _write_bem_rider_row(ws, x, entry.rider, event, is_20=True)
        except Exception as e:
            logger.error(f"Chyba BEM startovka řádek {x}: {e}")
        x += 1

    for entry in Entry.objects.filter(event=event.id, is_24=True, payment_complete=True, checkout=False):
        try:
            _write_bem_rider_row(ws, x, entry.rider, event, is_20=False)
        except Exception as e:
            logger.error(f"Chyba BEM startovka řádek {x}: {e}")
        x += 1

    for entry in EntryForeign.objects.filter(event=event.id, is_20=True, payment_complete=True, checkout=False):
        try:
            _write_bem_foreign_entry_row(ws, x, entry, is_20=True)
        except Exception as e:
            logger.error(f"Chyba BEM startovka cizinec řádek {x}: {e}")
        x += 1

    for entry in EntryForeign.objects.filter(event=event.id, is_24=True, payment_complete=True, checkout=False):
        try:
            _write_bem_foreign_entry_row(ws, x, entry, is_20=False)
        except Exception as e:
            logger.error(f"Chyba BEM startovka cizinec řádek {x}: {e}")
        x += 1

    file_path = _save_workbook_to_project_path(wb, file_name)
    event.bem_entries = file_name
    event.bem_entries_created = timezone.now()
    event.save()
    logger.info(f"BEM startovka vygenerována: {file_name}")
    return file_path


def _handle_bem_riders(request, event):
    """Vygeneruje BEM seznam všech aktivních jezdců (bez ohledu na přihlášení)."""
    file_name = f"media/riders-list/RIDERS_LIST_FOR_RACE_ID-{event.id}.xlsx"
    wb = Workbook()
    wb.encoding = "utf-8"
    ws = wb.active
    ws.title = "BEM5_EXT"
    ws = excel_first_line(ws)

    x = 2
    for rider in Rider.objects.filter(is_active=True, is_approved=True):
        # Jezdec může jezdit 20" i 24" — zapíše se do obou sloupců
        if rider.is_20:
            _write_bem_rider_row(ws, x, rider, event, is_20=True)
        if rider.is_24:
            # Cruiser třída jde do sloupce 21 (přepíše se i když is_20 bylo True)
            ws.cell(x, 21, resolve_event_classes(event, rider, is_20=False))
            ws.cell(x, 24, rider.plate_champ_20 or rider.plate_display)
            ws.cell(x, 25, rider.plate_champ_24 or rider.plate_display)
        x += 1

    file_path = _save_workbook_to_project_path(wb, file_name)
    event.bem_riders_list = file_name
    event.bem_riders_created = timezone.now()
    event.save()
    logger.info(f"BEM seznam jezdců vygenerován: {file_name}")
    return file_path


def _handle_rem_entries(request, event):
    """Vygeneruje REM soubor s online přihláškami (přihlášení jezdci)."""
    all_entries = REMRiders()
    all_entries.event = event
    all_entries.create_entries_list()
    logger.info(f"REM přihlášky vygenerovány pro závod {event.id}")
    event.refresh_from_db(fields=["rem_entries"])
    return event.rem_entries.path if event.rem_entries else None


def _handle_rem_riders(request, event):
    """Vygeneruje REM soubor se seznamem všech aktivních jezdců."""
    all_riders = REMRiders()
    all_riders.event = event
    all_riders.create_all_riders_list()
    logger.info(f"REM seznam jezdců vygenerován pro závod {event.id}")
    event.refresh_from_db(fields=["rem_riders_list"])
    return event.rem_riders_list.path if event.rem_riders_list else None


def _handle_upload_txt(request, event, pk):
    """Nahraje TSV výsledky z REM a zapíše pouze Result."""
    if "result-file-txt" not in request.FILES:
        messages.error(request, "Musíš vybrat soubor s výsledky závodu")
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": pk}))

    result_file = request.FILES["result-file-txt"]
    storage, filename, relative_path = _save_uploaded_file(result_file, "rem_results")

    results = SetResults()
    results.setEvent(pk)
    results.setFile(filename)
    results.run()

    event.rem_results = relative_path
    event.save(update_fields=["rem_results"])

    logger.info(f"REM výsledky nahrány pro závod {event.id}")
    audit_logger.info(
        "event_rem_results_uploaded admin_user_id=%s event_id=%s filename=%s",
        request.user.id,
        event.id,
        filename,
    )
    return None  # Pokračuj na shrnutí


def _handle_delete_txt(request, event, pk):
    """Smaže REM výsledky a přepočítá ranking."""
    Result.objects.filter(event=pk).delete()
    event.ccf_uploaded = False
    event.ccf_created = None
    event.save()
    schedule_ranking_recount()
    try:
        rem_path = event.rem_results.path
    except (ValueError, NotImplementedError):
        rem_path = None
    if rem_path:
        try:
            os.remove(rem_path)
        except FileNotFoundError:
            logger.warning(f"REM soubor nenalezen při mazání: {rem_path}")
    event.rem_results.delete(save=True)
    logger.info(f"REM výsledky smazány pro závod {event.id}")
    audit_logger.info(
        "event_rem_results_deleted admin_user_id=%s event_id=%s",
        request.user.id,
        event.id,
    )
    return None


# ===========================================================================
# VEŘEJNÉ VIEW FUNKCE
# ===========================================================================

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@staff_member_required
def event_admin_view(request, pk):
    """Hlavní admin panel závodu — dispečer akcí podle stisknutého tlačítka.

    Pro Evropský pohár/ME vrátí okamžitě EC stránku.
    Pro ostatní závodní typy zpracuje POST akci (btn-*) nebo zobrazí shrnutí.
    """
    event = get_object_or_404(Event.objects.select_related("organizer"), id=pk)

    # Evropský pohár a Mistrovství Evropy mají vlastní admin stránku
    if event.type_for_ranking in ["Evropský pohár", "Mistrovství Evropy"]:
        return _handle_ec_event(request, event)

    # Dispatch POST akcí — každý blok vrátí response nebo None
    if "btn-upload-result" in request.POST:
        response = _handle_upload_xls(request, event, pk)
        if response:
            return response

    elif "btn-delete-xls" in request.POST:
        return _handle_delete_xls(request, event, pk)

    elif "btn-bem-file" in request.POST:
        audit_logger.info("event_bem_entries_exported admin_user_id=%s event_id=%s", request.user.id, event.id)
        return _download_generated_file(_handle_bem_entries(request, event))

    elif "btn-riders-list" in request.POST:
        audit_logger.info("event_bem_riders_exported admin_user_id=%s event_id=%s", request.user.id, event.id)
        return _download_generated_file(_handle_bem_riders(request, event))

    elif "btn-rem-file" in request.POST:
        audit_logger.info("event_rem_entries_exported admin_user_id=%s event_id=%s", request.user.id, event.id)
        return _download_generated_file(_handle_rem_entries(request, event))

    elif "btn-rem-riders-list" in request.POST:
        audit_logger.info("event_rem_riders_exported admin_user_id=%s event_id=%s", request.user.id, event.id)
        return _download_generated_file(_handle_rem_riders(request, event))

    elif "btn-upload-txt" in request.POST:
        response = _handle_upload_txt(request, event, pk)
        if response:
            return response

    elif "btn-txt-delete" in request.POST:
        _handle_delete_txt(request, event, pk)

    elif "btn-generate-invoices" in request.POST:
        result = generate_event_invoices(event.id)
        if result["generated"]:
            messages.success(
                request,
                f"Vygenerováno {len(result['generated'])} faktur. Teď je můžeš upravit a následně odeslat.",
            )
        else:
            messages.warning(request, "Pro tento závod nebyly nalezeny žádné uhrazené registrace klubů k fakturaci.")

    elif "btn-send-notification" in request.POST:
        title = request.POST.get("notification_title", "").strip()
        body = request.POST.get("notification_body", "").strip()
        if not title or not body:
            messages.error(request, "Vyplň název i text notifikace.")
        else:
            user_ids = list(
                Entry.objects.filter(event=event, payment_complete=True)
                .exclude(user__isnull=True)
                .values_list("user_id", flat=True)
                .distinct()
            )
            result = (
                send_to_users(user_ids, title=title, body=body, path=f"/events/{event.pk}")
                if user_ids
                else {"success": 0}
            )
            messages.success(request, f"Notifikace odeslána na {result.get('success', 0)} zařízení.")

    elif "btn-send-invoices" in request.POST:
        generated = generate_event_invoices(event.id)
        result = send_event_invoices(event.id)
        if generated["generated"]:
            messages.success(
                request,
                (
                    f"Odesláno {len(result['sent'])} e-mailů, "
                    f"bez e-mailu zůstalo {len(result['skipped'])} klubů."
                ),
            )
        else:
            messages.warning(request, "Pro tento závod nebyly nalezeny žádné uhrazené registrace klubů k fakturaci.")

    # Shrnutí pro šablonu event-admin.html (zobrazí se vždy po akci nebo při GET)
    entries = Entry.objects.filter(event=event.id, payment_complete=True, checkout=False)
    foreign_entries = EntryForeign.objects.filter(event=event.id, payment_complete=True, checkout=False)
    sum_of_fees = sum((e.fee_beginner or 0) + (e.fee_20 or 0) + (e.fee_24 or 0) for e in entries)
    sum_of_fees += sum((e.fee_20 or 0) + (e.fee_24 or 0) for e in foreign_entries)

    notification_user_count = (
        Entry.objects.filter(event=event, payment_complete=True)
        .exclude(user__isnull=True)
        .values("user_id")
        .distinct()
        .count()
    )
    data = {
        "event": event,
        "invalid_licences": invalid_licence_in_event(event),
        "sum_of_fees": sum_of_fees,
        "sum_of_riders": entries.count() + foreign_entries.count(),
        "notification_user_count": notification_user_count,
        "asociation_fee": _resolve_association_fee(sum_of_fees, event.commission_fee),
        "results_exist": Result.objects.filter(event=event).exists(),
        "moto_runs_exist": RaceRun.objects.filter(event=event, round_type="MOTO").exists(),
        "prize_money_amount_toggle": PrizeMoneyPdfService().allows_amount_toggle(event),
        "is_mcr_club_teams_event": _is_mcr_club_teams_event(event),
    }
    return render(request, "event/event-admin.html", data)


@staff_member_required(login_url="/bmx-admin/login/")
def mcr_club_teams_admin_view(request, pk):
    event = get_object_or_404(Event.objects.select_related("organizer"), pk=pk)
    if not _is_mcr_club_teams_event(event):
        return _render_error_page(request, "Tato stránka je dostupná pouze pro závod Mistrovství ČR družstev.", status=404)

    teams = _get_mcr_club_teams_for_event(event)
    teams_count = teams.count()
    return render(
        request,
        "event/mcr-club-teams-admin.html",
        {
            "event": event,
            "year": _get_mcr_club_teams_year(event),
            "teams_count": teams_count,
            "riders_count": _get_mcr_club_teams_riders_count(event),
        },
    )


@staff_member_required(login_url="/bmx-admin/login/")
def mcr_club_teams_roster_view(request, pk):
    event = get_object_or_404(Event.objects.select_related("organizer"), pk=pk)
    if not _is_mcr_club_teams_event(event):
        return _render_error_page(request, "Soupis družstev je dostupný pouze pro závod Mistrovství ČR družstev.", status=404)

    teams = _get_mcr_club_teams_for_event(event)
    teams_count = teams.count()
    return render(
        request,
        "event/mcr-club-teams-roster.html",
        {
            "event": event,
            "year": _get_mcr_club_teams_year(event),
            "teams": teams,
            "teams_count": teams_count,
            "riders_count": _get_mcr_club_teams_riders_count(event),
        },
    )


@staff_member_required
def ec_by_club_xls(request, pk):
    """Export přihlášených jezdců na Evropský pohár seřazených po klubech (XLS)."""
    event = get_object_or_404(Event, pk=pk)
    clubs = Club.objects.filter(is_active=True).order_by("team_name")
    entries = Entry.objects.filter(
        event=pk,
        payment_complete=True,
        checkout=False,
    ).select_related("rider__club").order_by("rider")

    file_name = f"media/ec-files/EC_RACE_ID_BY_CLUB-{event.id}-{event.name}.xlsx"
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'

    wb = load_workbook(
        filename=os.path.join(settings.MEDIA_ROOT, "ec-files", "Club example - UEC.xlsx")
    )
    ws = wb.active
    ws.cell(3, 2, event.name)

    line = 6
    for club in clubs:
        for entry in entries:
            if entry.rider.club_id == club.id:
                ws.cell(line, 1, entry.rider.last_name)
                ws.cell(line, 2, entry.rider.first_name)
                ws.cell(line, 3, entry.rider.uci_id)
                ws.cell(line, 4, club.team_name)
                line += 1

    wb.save(response)
    return response


@login_required(login_url="/login/")
def summary_riders_in_event(request, pk):
    """Přehled počtu jezdců v každé třídě na závodě."""
    import json
    from collections import defaultdict
    event = get_object_or_404(Event, id=pk)
    category_counts = Counter()
    category_riders = defaultdict(list)

    czech_entries = Entry.objects.filter(event=pk, payment_complete=True, checkout=False).select_related("rider__club")
    foreign_entries = EntryForeign.objects.filter(event=pk, payment_complete=True, checkout=False)

    for entry in czech_entries:
        if entry.rider:
            name = f"{entry.rider.last_name} {entry.rider.first_name}"
            plate = entry.rider.plate_display or "—"
            club = entry.rider.club.team_name if entry.rider.club else "—"
        else:
            name = "—"
            plate = "—"
            club = "—"
        rider_item = {"plate": plate, "name": name, "club": club, "foreign": False}
        if entry.is_beginner and entry.class_beginner:
            category_counts[entry.class_beginner] += 1
            category_riders[entry.class_beginner].append(rider_item)
        if entry.is_20 and entry.class_20:
            category_counts[entry.class_20] += 1
            category_riders[entry.class_20].append(rider_item)
        if entry.is_24 and entry.class_24:
            category_counts[entry.class_24] += 1
            category_riders[entry.class_24].append(rider_item)

    for entry in foreign_entries:
        name = f"{entry.last_name} {entry.first_name}"
        plate = entry.plate or "—"
        club = entry.club or "—"
        rider_item = {"plate": plate, "name": name, "club": club, "foreign": True}
        if entry.is_20 and entry.class_20:
            category_counts[entry.class_20] += 1
            category_riders[entry.class_20].append(rider_item)
        if entry.is_24 and entry.class_24:
            category_counts[entry.class_24] += 1
            category_riders[entry.class_24].append(rider_item)

    count_20_24 = [
        SimpleNamespace(
            category_name=category_name,
            riders_in_category=riders_in_category,
        )
        for category_name, riders_in_category in sorted(category_counts.items())
        if category_name and "NENÍ VYPSÁNO" not in category_name and "není vypsáno" not in category_name
    ]

    riders_data = {
        cat: sorted(riders, key=lambda r: r["name"])
        for cat, riders in category_riders.items()
        if cat and "NENÍ VYPSÁNO" not in cat and "není vypsáno" not in cat
    }

    total_riders = sum(class_counter.riders_in_category for class_counter in count_20_24)
    return render(
        request,
        "event/riders-sum-event.html",
        {
            "event": event,
            "count_riders": count_20_24,
            "total_riders": total_riders,
            "riders_data_json": json.dumps(riders_data, ensure_ascii=False),
        },
    )


@commissar_pages_required
def commissar_assignments_view(request):
    """Přehled nasazení rozhodčích podle roku s volitelným editačním režimem."""
    year_options = list(_get_event_year_options())
    selected_year = _resolve_selected_year(request.GET.get("year"), year_options)
    can_edit = can_edit_commissar_assignments(request.user)
    edit_mode = can_edit and request.GET.get("edit") == "1"

    if request.method == "POST":
        if not can_edit:
            return HttpResponse(status=403)

        selected_year = _resolve_selected_year(request.POST.get("year"), year_options)
        events_to_update = list(
            Event.objects.filter(date__year=selected_year)
            .exclude(type_for_ranking__in=COMMISSAR_EXCLUDED_EVENT_TYPES)
            .select_related("pcp", "pcp_assist", "start_commissar")
            .order_by("date", "name")
        )

        active_commissars = {
            str(commissar.id): commissar
            for commissar in Commissar.objects.filter(is_active=True).order_by("last_name", "first_name")
        }

        validation_errors = []
        updated_events = []
        for event in events_to_update:
            original_values = {
                "pcp": event.pcp,
                "pcp_assist": event.pcp_assist,
                "start_commissar": event.start_commissar,
            }
            submitted_assignments = {}
            changed_fields = []
            has_conflict = False

            original_snapshot = {
                "pcp": str(event.pcp_id or ""),
                "pcp_assist": str(event.pcp_assist_id or ""),
                "start_commissar": str(event.start_commissar_id or ""),
            }
            for field_name, snapshot_value in original_snapshot.items():
                posted_snapshot = (request.POST.get(f"original_{field_name}_{event.id}") or "").strip()
                if posted_snapshot != snapshot_value:
                    validation_errors.append(
                        _("Závod %(event)s mezitím upravil někdo jiný. Obnov stránku a zkontroluj aktuální nasazení.")
                        % {"event": event.name}
                    )
                    has_conflict = True
                    break

            if has_conflict:
                continue

            for field_name in ("pcp", "pcp_assist", "start_commissar"):
                submitted_value = (request.POST.get(f"{field_name}_{event.id}") or "").strip()
                new_value = active_commissars.get(submitted_value) if submitted_value else None
                submitted_assignments[field_name] = new_value

            selected_ids = [
                commissar.id
                for commissar in submitted_assignments.values()
                if commissar is not None
            ]
            if len(selected_ids) != len(set(selected_ids)):
                validation_errors.append(
                    _("V závodu %(event)s nemůže být jeden rozhodčí nasazen do více rolí současně.")
                    % {"event": event.name}
                )
                continue

            for field_name, new_value in submitted_assignments.items():
                if getattr(event, field_name) != new_value:
                    setattr(event, field_name, new_value)
                    changed_fields.append(field_name)

            if changed_fields:
                event.save(update_fields=changed_fields)
                updated_events.append(event)
                for field_name in changed_fields:
                    previous = original_values[field_name] or "-"
                    current = getattr(event, field_name) or "-"
                    audit_logger.info(
                        "commissar_assignment_updated user_id=%s event_id=%s field=%s old=%s new=%s",
                        request.user.id,
                        event.id,
                        field_name,
                        previous,
                        current,
                    )

        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            return HttpResponseRedirect(
                f"{reverse('event:commissar-assignments')}?year={selected_year}&edit=1"
            )

        if updated_events:
            messages.success(request, _("Nasazení rozhodčích bylo uloženo."))
        else:
            messages.info(request, _("Nebyla provedena žádná změna."))

        return HttpResponseRedirect(
            f"{reverse('event:commissar-assignments')}?year={selected_year}"
        )

    events = (
        Event.objects.filter(date__year=selected_year)
        .exclude(type_for_ranking__in=COMMISSAR_EXCLUDED_EVENT_TYPES)
        .select_related("pcp", "pcp_assist", "start_commissar")
        .order_by("date", "name")
    )

    pcp_events_count = events.exclude(pcp__isnull=True).exclude(
        pcp__last_name=COMMISSAR_PLACEHOLDER_LAST_NAME
    ).count()
    pcp_assist_events_count = events.exclude(pcp_assist__isnull=True).exclude(
        pcp_assist__last_name=COMMISSAR_PLACEHOLDER_LAST_NAME
    ).count()
    start_commissar_events_count = events.exclude(start_commissar__isnull=True).exclude(
        start_commissar__last_name=COMMISSAR_PLACEHOLDER_LAST_NAME
    ).count()

    return render(request, "event/commissar-assignments.html", {
        "events": events,
        "selected_year": int(selected_year),
        "year_options": year_options,
        "can_edit_assignments": can_edit,
        "edit_mode": edit_mode,
        "active_commissars": Commissar.objects.filter(is_active=True).order_by("last_name", "first_name"),
        "pcp_events_count": pcp_events_count,
        "pcp_assist_events_count": pcp_assist_events_count,
        "start_commissar_events_count": start_commissar_events_count,
    })


@commissar_pages_required
def commissar_statistics_view(request):
    """Admin-only statistika nasazení rozhodčích podle roku."""
    year_options = list(_get_event_year_options())
    selected_year = _resolve_selected_year(request.GET.get("year"), year_options)

    commissars = (
        Commissar.objects.filter(is_active=True)
        .exclude(last_name=COMMISSAR_PLACEHOLDER_LAST_NAME)
        .annotate(
            pcp_count=Count(
                "PCP",
                filter=Q(PCP__date__year=selected_year)
                & ~Q(PCP__type_for_ranking__in=COMMISSAR_EXCLUDED_EVENT_TYPES),
                distinct=True,
            ),
            pcp_assist_count=Count(
                "PCP_asist",
                filter=Q(PCP_asist__date__year=selected_year)
                & ~Q(PCP_asist__type_for_ranking__in=COMMISSAR_EXCLUDED_EVENT_TYPES),
                distinct=True,
            ),
            start_commissar_count=Count(
                "start_commissar_events",
                filter=Q(start_commissar_events__date__year=selected_year)
                & ~Q(start_commissar_events__type_for_ranking__in=COMMISSAR_EXCLUDED_EVENT_TYPES),
                distinct=True,
            ),
        )
        .order_by("last_name", "first_name")
    )

    active_commissars_count = commissars.count()
    pcp_total = sum(commissar.pcp_count for commissar in commissars)
    pcp_assist_total = sum(commissar.pcp_assist_count for commissar in commissars)
    start_commissar_total = sum(commissar.start_commissar_count for commissar in commissars)

    return render(request, "event/commissar-statistics.html", {
        "commissars": commissars,
        "selected_year": int(selected_year),
        "year_options": year_options,
        "active_commissars_count": active_commissars_count,
        "pcp_total": pcp_total,
        "pcp_assist_total": pcp_assist_total,
        "start_commissar_total": start_commissar_total,
    })


@login_required(login_url="/login/")
@staff_member_required
def export_event_results(request, event_id):
    """Odešle výsledky závodu do API ČSC (Czech Cycling Federation).

    Výsledky jsou odesílány jednorázově — po odeslání je závod označen ccf_uploaded=True.
    """
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return _render_error_page(request, "Závod nebyl nalezen.", status=404)

    if event.ccf_uploaded:
        sent_at = event.ccf_created.strftime("%d.%m.%Y %H:%M:%S") if event.ccf_created else "v minulosti"
        return _render_error_page(
            request,
            "Výsledky už byly odeslány.",
            detail=f"Závod {event.name} byl již odeslán {sent_at}.",
            status=409,
        )

    token = get_api_token()
    if not token:
        return _render_error_page(
            request,
            "Nepodařilo se získat token pro přihlášení k API ČSC.",
            status=502,
        )

    results = list(Result.objects.filter(event=event).select_related("rider__club"))
    payload = []
    category_breakdown = Counter()
    skipped_results = 0

    for res in results:
        rider = res.rider
        if not rider:
            logger.warning(f"Výsledek {res.pk} nemá přiřazeného jezdce, přeskakuji.")
            skipped_results += 1
            continue

        cruiser = not res.is_20 and not res.is_beginner
        category_code = resolve_api_category_code(
            rider=rider, is_20=res.is_20, is_24=cruiser, is_beginner=res.is_beginner
        )
        category_breakdown[category_code or _("Bez kódu")] += 1

        payload.append({
            "category": category_code,
            "rank": res.place,
            "bib": rider.plate_display,
            "uciid": str(rider.uci_id or ""),
            "lastName": rider.last_name,
            "firstName": rider.first_name,
            "country": res.country,
            "team": rider.club.team_name if rider.club else "",
            "gender": "F" if rider.gender == "Žena" else "M",
            "phase": "",
            "heat": "",
            "result": str(res.place),
            "irm": "",
            "sortOrder": res.place,
        })

    api_url = (
        f"https://portal.api.czechcyclingfederation.com/api/services/saveraceresults"
        f"?raceId={event.ccf_id}&subDisciplineCode=BMX_RAC"
    )

    try:
        logger.info(
            "Odesílám výsledky do API ČSC pro event_id=%s, race_id=%s, payload_items=%s",
            event.id,
            event.ccf_id,
            len(payload),
        )
        response = requests.post(
            api_url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=CCF_API_TIMEOUT,
        )
        response.raise_for_status()
        payload_dir = os.path.join(settings.MEDIA_ROOT, "api-payloads")
        os.makedirs(payload_dir, exist_ok=True)
        with open(
            os.path.join(payload_dir, f"payload_event_{event.id}.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("Výsledky úspěšně odeslány do API ČSC pro event_id=%s", event.id)
    except requests.Timeout:
        logger.exception("Timeout při odesílání výsledků do API ČSC pro event_id=%s", event.id)
        return _render_error_page(
            request,
            "Nepodařilo se odeslat výsledky na API.",
            detail="API ČSC neodpovědělo včas.",
            status=504,
        )
    except requests.RequestException as e:
        logger.exception("Chyba při odesílání výsledků do API ČSC pro event_id=%s", event.id)
        return _render_error_page(
            request,
            "Nepodařilo se odeslat výsledky na API.",
            detail=str(e),
            status=502,
        )

    event.ccf_created = now()
    event.ccf_uploaded = True
    event.save()
    audit_logger.info(
        "event_results_exported_to_ccf admin_user_id=%s event_id=%s sent_count=%s",
        request.user.id,
        event.id,
        len(payload),
    )

    sent_count = len(payload)
    total_results = len(results)

    def _pct(value, total):
        if not total:
            return 0
        return round((value / total) * 100)

    export_summary = {
        "total_results": total_results,
        "sent_count": sent_count,
        "skipped_count": skipped_results,
        "sent_ratio": _pct(sent_count, total_results),
        "women_count": sum(1 for item in payload if item["gender"] == "F"),
        "men_count": sum(1 for item in payload if item["gender"] == "M"),
        "czech_count": sum(1 for item in payload if (item["country"] or "").upper() == "CZE"),
        "foreign_count": sum(1 for item in payload if (item["country"] or "").upper() != "CZE"),
        "bike20_count": sum(1 for res in results if res.rider and res.is_20 and not res.is_beginner),
        "cruiser_count": sum(1 for res in results if res.rider and not res.is_20 and not res.is_beginner),
        "beginner_count": sum(1 for res in results if res.rider and res.is_beginner),
        "with_uci_count": sum(1 for item in payload if item["uciid"]),
        "with_bib_count": sum(1 for item in payload if item["bib"]),
        "with_team_count": sum(1 for item in payload if item["team"]),
        "unique_teams_count": len({item["team"] for item in payload if item["team"]}),
        "unique_categories_count": len({item["category"] for item in payload if item["category"]}),
        "top_categories": [
            {"label": label, "count": count, "percent": _pct(count, sent_count)}
            for label, count in category_breakdown.most_common(5)
        ],
        "coverage_metrics": [
            {"label": _("Spárovaní jezdci"), "value": sent_count, "total": total_results, "percent": _pct(sent_count, total_results)},
            {"label": _("UCI ID"), "value": sum(1 for item in payload if item["uciid"]), "total": sent_count, "percent": _pct(sum(1 for item in payload if item["uciid"]), sent_count)},
            {"label": _("Startovní číslo"), "value": sum(1 for item in payload if item["bib"]), "total": sent_count, "percent": _pct(sum(1 for item in payload if item["bib"]), sent_count)},
            {"label": _("Klub / tým"), "value": sum(1 for item in payload if item["team"]), "total": sent_count, "percent": _pct(sum(1 for item in payload if item["team"]), sent_count)},
        ],
    }

    return render(request, "event/results_sent.html", {
        "event": event,
        "sent_count": sent_count,
        "export_summary": export_summary,
    })


@login_required(login_url="/login/")
@staff_member_required
def export_uci_results(request, event_id):
    event = get_object_or_404(Event.objects.select_related("classes_and_fees_like"), id=event_id)
    logger.info("Spouštím UCI export pro event_id=%s", event.id)

    if not event.is_uci_race:
        logger.warning("UCI export odmítnut: event_id=%s není UCI závod", event.id)
        messages.error(request, _("Tento závod není označen jako UCI závod."))
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": event.id}))

    if not os.path.exists(UCI_EXPORT_TEMPLATE):
        logger.error("UCI export selhal: chybí šablona %s", UCI_EXPORT_TEMPLATE)
        messages.error(request, _("Chybí UCI XLSX šablona pro export."))
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": event.id}))

    if not event.uci_event_code.strip():
        logger.warning("UCI export odmítnut: event_id=%s nemá UCI_EVENT_CODE", event.id)
        messages.error(request, _("U závodu chybí UCI_EVENT_CODE."))
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": event.id}))

    missing_competition_codes = get_missing_uci_competition_codes(event)
    if missing_competition_codes:
        logger.warning(
            "UCI export odmítnut: event_id=%s chybí competition codes %s",
            event.id,
            ", ".join(missing_competition_codes),
        )
        messages.error(
            request,
            _("U závodu chybí některé UCI kódy kategorií: %(fields)s.")
            % {"fields": ", ".join(missing_competition_codes)},
        )
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": event.id}))

    zip_name, zip_bytes, export_metadata = generate_uci_export_zip(event, UCI_EXPORT_TEMPLATE)
    for item in export_metadata:
        logger.info(
            "UCI export kategorie vygenerován pro event_id=%s, slug=%s, rows=%s",
            event.id,
            item["slug"],
            item["rows"],
        )

    logger.info(
        "UCI export ZIP připraven pro event_id=%s, files=%s, zip_name=%s",
        event.id,
        len(export_metadata),
        zip_name,
    )
    audit_logger.info(
        "event_uci_export_generated admin_user_id=%s event_id=%s files=%s zip_name=%s",
        request.user.id,
        event.id,
        len(export_metadata),
        zip_name,
    )
    response = HttpResponse(zip_bytes, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    return response


@login_required(login_url="/login/")
@staff_member_required
def unpaid_moto_riders_report(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if not RaceRun.objects.filter(event=event, round_type="MOTO").exists():
        messages.error(request, _("Pro tento závod zatím nejsou nahrané žádné MOTO jízdy v RaceRun."))
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": pk}))

    report = build_unpaid_moto_report(event)
    audit_logger.info(
        "event_unpaid_moto_report_opened admin_user_id=%s event_id=%s unmatched=%s no_uci=%s",
        request.user.id,
        event.id,
        len(report.get("unpaid_riders", [])),
        len(report.get("riders_without_uci", [])),
    )
    return render(
        request,
        "event/unpaid-moto-riders-report.html",
        {
            "event": event,
            **report,
        },
    )


@login_required(login_url="/login/")
@staff_member_required
def unpaid_moto_riders_report_pdf(request, pk):
    event = get_object_or_404(Event, pk=pk)

    if not RaceRun.objects.filter(event=event, round_type="MOTO").exists():
        messages.error(request, _("Pro tento závod zatím nejsou nahrané žádné MOTO jízdy v RaceRun."))
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": pk}))

    report = build_unpaid_moto_report(event)
    service = UnpaidMotoReportPdfService()
    pdf_bytes = service.build_pdf(event, report)
    audit_logger.info(
        "event_unpaid_moto_report_pdf_generated admin_user_id=%s event_id=%s unmatched=%s no_uci=%s",
        request.user.id,
        event.id,
        len(report.get("unpaid_riders", [])),
        len(report.get("riders_without_uci", [])),
    )

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{service.build_filename(event)}"'
    return response


@login_required(login_url="/login/")
@staff_member_required
def send_invoices(request, pk):
    """Rozesílání faktur klubům pro daný závod."""
    generated = generate_event_invoices(pk)
    result = send_event_invoices(pk)
    audit_logger.info(
        "event_invoices_generated admin_user_id=%s event_id=%s sent_count=%s",
        request.user.id,
        pk,
        len(result["sent"]),
    )
    return render(request, "event/results_sent.html", {
        "event": get_object_or_404(Event, pk=pk),
        "sent_count": len(result["sent"]),
        "export_summary": {
            "total_results": len(generated["generated"]),
            "sent_count": len(result["sent"]),
            "skipped_count": len(result["skipped"]),
            "sent_ratio": round((len(result["sent"]) / len(generated["generated"])) * 100) if generated["generated"] else 0,
            "women_count": 0,
            "men_count": 0,
            "czech_count": 0,
            "foreign_count": 0,
            "bike20_count": 0,
            "cruiser_count": 0,
            "beginner_count": 0,
            "unique_teams_count": 0,
            "unique_categories_count": 0,
            "coverage_metrics": [],
            "top_categories": [],
        },
    })


@login_required(login_url="/login/")
@staff_member_required
def price_money_pdf(request, pk):
    """PDF potvrzení převzetí prize money."""
    event = get_object_or_404(Event.objects.select_related("organizer"), pk=pk)
    service = PrizeMoneyPdfService()
    include_amounts = request.GET.get("amounts", "1") != "0"
    if not service.allows_amount_toggle(event):
        include_amounts = True

    try:
        pdf_bytes = service.build_pdf(event, include_amounts=include_amounts)
    except ValueError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": pk}))
    audit_logger.info(
        "event_prize_money_pdf_generated admin_user_id=%s event_id=%s include_amounts=%s",
        request.user.id,
        event.id,
        include_amounts,
    )

    suffix = "with-amounts" if include_amounts else "without-amounts"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="prize-money-{event.id}-{suffix}-{timezone.now().strftime("%Y%m%d%H%M%S")}.pdf"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


_VALID_STATS_KEYS = START_KEYS | RESULT_KEYS | {"overall_results"}

_STATS_SECTION_LABELS = {
    "motos": "Motos – listina",
    "motos_results": "Motos – výsledky",
    "1_16": "1/16 – listina",
    "1_16_results": "1/16 – výsledky",
    "1_8": "1/8 – listina",
    "1_8_results": "1/8 – výsledky",
    "1_4": "1/4 – listina",
    "1_4_results": "1/4 – výsledky",
    "1_2": "1/2 – listina",
    "1_2_results": "1/2 – výsledky",
    "final": "Finále – listina",
    "final_results": "Finále – výsledky",
    "overall_results": "Celkové výsledky",
}

_ROUND_TYPE_LABELS = {
    "MOTO": "Motos",
    "F16": "1/16",
    "F8": "1/8",
    "F4": "1/4",
    "F2": "1/2",
    "FINAL": "Finále",
}
_ROUND_TYPE_ORDER = ["MOTO", "F16", "F8", "F4", "F2", "FINAL"]
_MAX_STATS_FILE_SIZE = 2 * 1024 * 1024  # 2 MB


def _format_import_message(import_result):
    total = import_result["created"]
    counts = import_result.get("counts_by_round", {})
    parts = [
        f"{_ROUND_TYPE_LABELS.get(rt, rt)}: {counts[rt]}"
        for rt in _ROUND_TYPE_ORDER
        if rt in counts
    ]
    msg = _("RaceRun aktualizován, zapsáno {count} jízd").format(count=total)
    if parts:
        msg += " (" + ", ".join(parts) + ")"
    return msg + "."


def _warn_unmatched_riders(request, unmatched):
    if not unmatched:
        return
    MAX_SHOWN = 10
    shown = unmatched[:MAX_SHOWN]
    rest = len(unmatched) - MAX_SHOWN
    parts = [
        f"{item['category']} — {item['plate']} {item['name']}".strip(" —")
        for item in shown
    ]
    msg = _("Tito závodníci nebyli nalezeni v databázi: ") + "; ".join(parts)
    if rest > 0:
        msg += _(" (a {n} dalších)").format(n=rest)
    messages.warning(request, msg)


def _handle_stats_delete_key(request, event, pk):
    delete_key = request.POST.get("delete_key", "").strip()
    if delete_key not in _VALID_STATS_KEYS:
        messages.error(request, _("Neplatný klíč pro smazání."))
        return redirect("event:import-stats", pk=pk)

    deleted_count = _delete_uploaded_files_by_prefix("event_stats", str(pk), prefix=delete_key)
    import_result = RaceRunImportService().import_event_runs(event)
    audit_logger.info(
        "event_stats_file_deleted admin_user_id=%s event_id=%s delete_key=%s deleted_files=%s imported_runs=%s",
        request.user.id, event.id, delete_key, deleted_count, import_result["created"],
    )
    if deleted_count > 0:
        messages.success(request, _("Soubor pro vybranou sekci byl smazán."))
        messages.info(request, _format_import_message(import_result))
        _warn_unmatched_riders(request, import_result["unmatched"])
    else:
        messages.info(request, _("Pro vybranou sekci nebyl nalezen žádný soubor."))
    return redirect("event:import-stats", pk=pk)


def _handle_stats_delete_all(request, event, pk):
    stats_dir = os.path.join(settings.MEDIA_ROOT, "event_stats", str(pk))
    deleted_count = 0
    if os.path.exists(stats_dir):
        for f in os.listdir(stats_dir):
            file_path = os.path.join(stats_dir, f)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    logger.error("Nepodařilo se smazat soubor %s: %s", file_path, e)
    RaceRun.objects.filter(event=event).delete()
    audit_logger.info(
        "event_stats_deleted admin_user_id=%s event_id=%s deleted_files=%s",
        request.user.id, event.id, deleted_count,
    )
    if deleted_count > 0:
        messages.success(request, _("Všechny statistiky byly smazány."))
    else:
        messages.info(request, _("Žádné soubory k smazání."))
    return redirect("event:import-stats", pk=pk)


def _handle_stats_file_upload(request, event, pk):
    count = 0
    uploaded_labels = []
    for key in request.FILES:
        file = request.FILES[key]
        if not file.name.lower().endswith(".html"):
            continue
        if file.size > _MAX_STATS_FILE_SIZE:
            messages.warning(
                request,
                _("Soubor {name} je příliš velký ({size} kB), maximum je 2 MB.").format(
                    name=file.name, size=file.size // 1024
                ),
            )
            continue
        _delete_uploaded_files_by_prefix("event_stats", str(pk), prefix=key)
        original_name = os.path.basename(file.name)
        file.name = f"{key}__{original_name}"
        _save_uploaded_file(file, "event_stats", str(pk))
        count += 1
        uploaded_labels.append(_STATS_SECTION_LABELS.get(key, key))

    if count > 0:
        results_count = Result.objects.filter(event=event).count()
        import_result = RaceRunImportService().import_event_runs(event)
        audit_logger.info(
            "event_stats_imported admin_user_id=%s event_id=%s uploaded_files=%s imported_runs=%s results_count=%s",
            request.user.id, event.id, count, import_result["created"], results_count,
        )
        messages.success(
            request,
            _("Nahráno ({count}): {names}.").format(count=count, names=", ".join(uploaded_labels)),
        )
        messages.info(request, _format_import_message(import_result))
        if results_count == 0:
            messages.warning(
                request,
                _(
                    "Pro tento závod nejsou v databázi žádné výsledky (Result), takže statistické jízdy nešlo s nikým spárovat. Nejdřív nahraj výsledky závodu do Result a potom spusť import statistik znovu."
                ),
            )
        elif import_result["created"] == 0:
            messages.warning(
                request,
                _(
                    "Statistické soubory se nahrály, ale nevznikl žádný RaceRun. Zkontroluj, že kategorie, jména a čísla v HTML odpovídají výsledkům uloženým v Result."
                ),
            )
        _warn_unmatched_riders(request, import_result["unmatched"])
    else:
        messages.warning(request, _("Nebyly nahrány žádné soubory (povoleny jsou pouze .html)."))
    return redirect("event:import-stats", pk=pk)


@login_required(login_url="/login/")
@staff_member_required
def import_event_stats(request, pk):
    """Stránka pro import statistických údajů závodu."""
    event = get_object_or_404(Event, pk=pk)

    if request.method == "POST":
        if "delete_key" in request.POST:
            return _handle_stats_delete_key(request, event, pk)
        if "delete_all" in request.POST:
            return _handle_stats_delete_all(request, event, pk)
        if request.FILES:
            return _handle_stats_file_upload(request, event, pk)
        return redirect("event:import-stats", pk=pk)

    # Načtení existujících souborů
    uploaded_files = []
    uploaded_files_by_key = {}
    stats_dir = os.path.join(settings.MEDIA_ROOT, "event_stats", str(pk))

    upload_sections = [
        {
            "title": _("Motos (Rozjížďky)"),
            "fields": [
                {"name": "motos", "label": _("Startovní listina")},
                {"name": "motos_results", "label": _("Výsledky")},
            ],
        },
        {
            "title": _("1/16 Finále"),
            "fields": [
                {"name": "1_16", "label": _("Startovní listina")},
                {"name": "1_16_results", "label": _("Výsledky")},
            ],
        },
        {
            "title": _("1/8 Finále"),
            "fields": [
                {"name": "1_8", "label": _("Startovní listina")},
                {"name": "1_8_results", "label": _("Výsledky")},
            ],
        },
        {
            "title": _("1/4 Finále"),
            "fields": [
                {"name": "1_4", "label": _("Startovní listina")},
                {"name": "1_4_results", "label": _("Výsledky")},
            ],
        },
        {
            "title": _("1/2 Finále"),
            "fields": [
                {"name": "1_2", "label": _("Startovní listina")},
                {"name": "1_2_results", "label": _("Výsledky")},
            ],
        },
        {
            "title": _("Finále"),
            "fields": [
                {"name": "final", "label": _("Startovní listina")},
                {"name": "final_results", "label": _("Výsledky")},
            ],
        },
    ]
    overall_results_field = {
        "name": "overall_results",
        "section_title": _("Celkové výsledky"),
        "label": _("Soubor s celkovými výsledky"),
    }

    category_map = {}
    for section in upload_sections:
        for field in section["fields"]:
            category_map[field["name"]] = _("%(section)s - %(label)s") % {
                "section": section["title"],
                "label": field["label"],
            }
    category_map["overall_results"] = _("Celkové výsledky")

    if os.path.exists(stats_dir):
        for f in os.listdir(stats_dir):
            if os.path.isfile(os.path.join(stats_dir, f)):
                parts = f.split("__", 1)
                key = parts[0]
                original_name = parts[1] if len(parts) > 1 else f
                
                file_info = {
                    "key": key,
                    "filename": f,
                    "original_name": original_name,
                    "label": category_map.get(key, _("Neznámá kategorie")),
                    "url": f"{settings.MEDIA_URL}event_stats/{pk}/{f}",
                    "created": datetime.datetime.fromtimestamp(os.path.getctime(os.path.join(stats_dir, f))),
                }
                uploaded_files.append(file_info)
                uploaded_files_by_key[key] = file_info
    
    uploaded_files.sort(key=lambda x: x['label'])

    for section in upload_sections:
        for field in section["fields"]:
            field["uploaded_file"] = uploaded_files_by_key.get(field["name"])
    overall_results_field["uploaded_file"] = uploaded_files_by_key.get(overall_results_field["name"])

    phase_warnings = []
    for section in upload_sections:
        keys = [field["name"] for field in section["fields"]]
        has_start = keys[0] in uploaded_files_by_key
        has_results = keys[1] in uploaded_files_by_key
        if has_start and not has_results:
            phase_warnings.append(
                _("{section}: nahrána startovní listina, chybí výsledky").format(section=section["title"])
            )
        elif has_results and not has_start:
            phase_warnings.append(
                _("{section}: nahrány výsledky, chybí startovní listina").format(section=section["title"])
            )

    return render(
        request,
        "event/import-stats.html",
        {
            "event": event,
            "uploaded_files": uploaded_files,
            "upload_sections": upload_sections,
            "overall_results_field": overall_results_field,
            "phase_warnings": phase_warnings,
        },
    )
