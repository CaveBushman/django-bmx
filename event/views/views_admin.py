"""
event/views/views_admin.py — admin a komisařské operace

Obsah:
  Veřejné view funkce (URL handlery):
    - event_admin_view       — hlavní admin panel závodu
    - find_payment_view      — vyhledání platby
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
import tempfile
import zipfile
from collections import Counter
import requests
from datetime import date
from types import SimpleNamespace
from django.shortcuts import get_object_or_404, render, reverse, HttpResponseRedirect, redirect
from django.http import FileResponse, HttpResponse
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.cache import cache_control
from django.utils.translation import gettext as _
from event.models import Event, Entry, EntryForeign, Result, RaceRun
from rider.models import Rider
from rider.plates import display_plate
from club.models import Club
from commissar.models import Commissar
from event.func import (
    invalid_licence_in_event, clean_classes_on_event,
    excel_first_line, expire_licence, gender_resolve,
    gender_resolve_small_letter, team_name_resolve, resolve_event_classes,
    foreign_club_resolve,
    SetResults,
)
from event.entry import NumberInEvent, REMRiders
from event.result import GetResult
from ranking.ranking import schedule_ranking_recount
from rider.rider import (
    get_api_token,
    generate_insurance_file,
    resolve_api_category_code,
    trigger_cn_qualification_recount_if_needed,
)
from finance.invoices import generate_event_invoices
from event.prize_money import PrizeMoneyPdfService
from event.services.race_run_import import RaceRunImportService
from openpyxl import Workbook, load_workbook
import pandas as pd
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)

COMMISSAR_EXCLUDED_EVENT_TYPES = [
    "Evropský pohár",
    "Mistrovství Evropy",
    "Mistrovství světa",
    "Světový pohár",
]

COMMISSAR_PLACEHOLDER_LAST_NAME = "Bude upřesněno"

UCI_EXPORT_TEMPLATE = os.path.join(settings.MEDIA_ROOT, "uci-templates", "uci-results-template.xlsx")
UCI_EXPORT_CATEGORY_CONFIG = (
    ("women_elite", "Women Elite", "uci_code_women_elite"),
    ("men_elite", "Men Elite", "uci_code_men_elite"),
    ("women_u23", "Women Under 23", "uci_code_women_under_23"),
    ("men_u23", "Men Under 23", "uci_code_men_under_23"),
    ("women_junior", "Women Junior", "uci_code_women_junior"),
    ("men_junior", "Men Junior", "uci_code_men_junior"),
)


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


def _sanitize_export_filename(value):
    safe = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in str(value or ""))
    return safe.strip("_") or "export"


def _format_uci_rank_suffix(rank):
    try:
        rank_int = int(rank)
    except (TypeError, ValueError):
        return str(rank or "")

    if 10 <= rank_int % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank_int % 10, "th")
    return f"{rank_int}{suffix}"


def _resolve_uci_finish_time(event, result):
    runs = (
        RaceRun.objects.filter(event=event, rider_id=result.rider_id, finish_time__isnull=False)
        .order_by("-updated", "-created", "-id")
    )
    final_run = runs.filter(round_type="FINAL").first()
    if final_run and final_run.finish_time is not None:
        return final_run.finish_time
    fallback_run = runs.first()
    return fallback_run.finish_time if fallback_run else None


def _build_uci_export_rows(event, rider_class_name):
    rows = []
    results = (
        Result.objects.filter(event=event, rider__class_20=rider_class_name)
        .select_related("rider__club")
        .order_by("place", "last_name", "first_name")
    )

    subgroup_rank = 0
    for result in results:
        rider = result.rider
        if not rider:
            continue
        subgroup_rank += 1

        finish_time = _resolve_uci_finish_time(event, result)
        rows.append({
            "rank": subgroup_rank,
            "bib": display_plate(rider) or "",
            "uci_id": rider.uci_id,
            "last_name": result.last_name or rider.last_name or "",
            "first_name": result.first_name or rider.first_name or "",
            "country": result.country or "CZE",
            "team": rider.club.team_name if rider.club else (result.club or ""),
            "gender": "W" if rider.gender == "Žena" else "M",
            "phase": "Final",
            "heat": 1,
            "result": (
                f"{_format_uci_rank_suffix(subgroup_rank)}, {finish_time:.3f}"
                if finish_time is not None
                else _format_uci_rank_suffix(subgroup_rank)
            ),
            "irm": "",
        })

    return rows


def _write_uci_export_workbook(template_path, destination_path, competition_code, event_code, rows):
    wb = load_workbook(template_path)
    general_ws = wb["General"]
    results_ws = wb["Results"]

    general_ws["B4"] = competition_code
    general_ws["B5"] = event_code

    row_index = 2
    for row in rows:
        results_ws.cell(row_index, 1, row["rank"])
        results_ws.cell(row_index, 2, row["bib"])
        results_ws.cell(row_index, 3, row["uci_id"])
        results_ws.cell(row_index, 4, row["last_name"])
        results_ws.cell(row_index, 5, row["first_name"])
        results_ws.cell(row_index, 6, row["country"])
        results_ws.cell(row_index, 7, row["team"])
        results_ws.cell(row_index, 8, row["gender"])
        results_ws.cell(row_index, 9, row["phase"])
        results_ws.cell(row_index, 10, row["heat"])
        results_ws.cell(row_index, 11, row["result"])
        results_ws.cell(row_index, 12, row["irm"])
        row_index += 1

    wb.save(destination_path)


# ===========================================================================
# PRIVÁTNÍ HELPERY — volány z event_admin_view
# Každý helper zpracuje jeden btn-* blok a vrátí response nebo None.
# None = pokračuj dál (zobraz shrnutí), response = okamžitý redirect/render.
# ===========================================================================

def _handle_ec_event(request, event):
    """Generuje EC přihlašovací soubor pro UEC (Evropský pohár / ME)."""
    token = get_api_token()

    payments = 0
    entries = Entry.objects.filter(
        event=event.id, payment_complete=True, checkout=False
    ).select_related("rider")
    sum_entries = entries.filter(is_20=True).count() + entries.filter(is_24=True).count()

    # Načti šablonu UEC souboru podle typu závodu
    file_name = f"media/ec-files/EC_RACE_ID-{event.id}-{event.name}.xlsx"
    template = (
        "media/ec-files/Entries example - UEC.xlsx"
        if event.type_for_ranking == "Evropský pohár"
        else "media/ec-files/Entries_upload_UEC_Champ_2024.xlsx"
    )
    wb = load_workbook(filename=template)
    ws = wb.active

    x = 3
    for entry in entries:
        rider = entry.rider
        try:
            ws.cell(x, 2, rider.uci_id)
            ws.cell(x, 3, rider.date_of_birth)
            ws.cell(x, 4, rider.first_name)
            ws.cell(x, 5, rider.last_name)
            ws.cell(x, 6, gender_resolve_small_letter(rider.gender))
            ws.cell(x, 7, rider.transponder_20 if entry.is_20 else rider.transponder_24)
            if entry.is_24:
                ws.cell(x, 8, "x")
            if entry.is_20:
                if rider.is_elite:
                    ws.cell(x, 9, "x")
                if rider.class_20 in ["Women Under 23", "Men Under 23"]:
                    ws.cell(x, 10, "x")
            x += 1
        except Exception as e:
            logger.error(f"Chyba při zápisu do EC souboru: {e}")

        payments += entry.fee_20 if entry.is_20 else entry.fee_24

    wb.save(file_name)
    event.ec_file = file_name
    event.ec_file_created = timezone.now()
    event.save()

    # Vygeneruj pojistný seznam pro UEC
    generate_insurance_file(event)

    return render(request, "event/event-admin-ec.html", {
        "event": event,
        "sum_entries": sum_entries,
        "payments": payments,
    })


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

    wb.save(file_name)
    event.bem_entries = file_name
    event.bem_entries_created = timezone.now()
    event.save()
    logger.info(f"BEM startovka vygenerována: {file_name}")
    return os.path.join(settings.BASE_DIR, file_name)


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

    wb.save(file_name)
    event.bem_riders_list = file_name
    event.bem_riders_created = timezone.now()
    event.save()
    logger.info(f"BEM seznam jezdců vygenerován: {file_name}")
    return os.path.join(settings.BASE_DIR, file_name)


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
    event = Event.objects.get(id=pk)

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
        return _download_generated_file(_handle_bem_entries(request, event))

    elif "btn-riders-list" in request.POST:
        return _download_generated_file(_handle_bem_riders(request, event))

    elif "btn-rem-file" in request.POST:
        return _download_generated_file(_handle_rem_entries(request, event))

    elif "btn-rem-riders-list" in request.POST:
        return _download_generated_file(_handle_rem_riders(request, event))

    elif "btn-upload-txt" in request.POST:
        response = _handle_upload_txt(request, event, pk)
        if response:
            return response

    elif "btn-txt-delete" in request.POST:
        _handle_delete_txt(request, event, pk)

    # Shrnutí pro šablonu event-admin.html (zobrazí se vždy po akci nebo při GET)
    entries = Entry.objects.filter(event=event.id, payment_complete=True, checkout=False)
    sum_of_fees = sum(e.fee_beginner + e.fee_20 + e.fee_24 for e in entries)

    data = {
        "event": event,
        "invalid_licences": invalid_licence_in_event(event),
        "sum_of_fees": sum_of_fees,
        "sum_of_riders": entries.count(),
        "asociation_fee": int(sum_of_fees * event.commission_fee / 100),
        "results_exist": Result.objects.filter(event=event).exists(),
        "prize_money_amount_toggle": PrizeMoneyPdfService().allows_amount_toggle(event),
    }
    return render(request, "event/event-admin.html", data)


@staff_member_required
def find_payment_view(request):
    """Vyhledá platební záznam k jezdci a závodu."""
    events = Event.objects.all()

    if "find-payment" in request.POST:
        try:
            rider_uci = request.POST["rider"]
            event_id = request.POST["event"]
            entry = Entry.objects.get(event=event_id, rider=rider_uci, payment_complete=True)
            rider = Rider.objects.get(uci_id=rider_uci)
            event = Event.objects.get(id=event_id)
            return render(request, "event/find-payment.html", {
                "event": event, "rider": rider, "entry": entry
            })
        except Exception:
            pass

    return render(request, "event/find-payment.html", {"events": events})


@staff_member_required
def ec_by_club_xls(request, pk):
    """Export přihlášených jezdců na Evropský pohár seřazených po klubech (XLS)."""
    event = get_object_or_404(Event, pk=pk)
    clubs = Club.objects.filter(is_active=True).order_by("team_name")
    entries = Entry.objects.filter(event=pk, payment_complete=True).select_related("rider__club").order_by("rider")

    file_name = f"media/ec-files/EC_RACE_ID_BY_CLUB-{event.id}-{event.name}.xlsx"
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'

    wb = load_workbook(filename="media/ec-files/Club example - UEC.xlsx")
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


def summary_riders_in_event(request, pk):
    """Přehled počtu jezdců v každé třídě na závodě."""
    event = Event.objects.get(id=pk)
    category_counts = Counter()

    czech_entries = Entry.objects.filter(event=pk, payment_complete=True, checkout=False)
    foreign_entries = EntryForeign.objects.filter(event=pk, payment_complete=True, checkout=False)

    for entry in czech_entries:
        if entry.is_beginner and entry.class_beginner:
            category_counts[entry.class_beginner] += 1
        if entry.is_20 and entry.class_20:
            category_counts[entry.class_20] += 1
        if entry.is_24 and entry.class_24:
            category_counts[entry.class_24] += 1

    for entry in foreign_entries:
        if entry.is_20 and entry.class_20:
            category_counts[entry.class_20] += 1
        if entry.is_24 and entry.class_24:
            category_counts[entry.class_24] += 1

    count_20_24 = [
        SimpleNamespace(category_name=category_name, riders_in_category=riders_in_category)
        for category_name, riders_in_category in sorted(category_counts.items())
        if category_name and "NENÍ VYPSÁNO" not in category_name and "není vypsáno" not in category_name
    ]

    total_riders = sum(class_counter.riders_in_category for class_counter in count_20_24)
    return render(
        request,
        "event/riders-sum-event.html",
        {
            "event": event,
            "count_riders": count_20_24,
            "total_riders": total_riders,
        },
    )


@staff_member_required
def commissar_assignments_view(request):
    """Admin-only přehled nasazení rozhodčích podle roku."""
    year_options = list(_get_event_year_options())
    selected_year = _resolve_selected_year(request.GET.get("year"), year_options)

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
        "pcp_events_count": pcp_events_count,
        "pcp_assist_events_count": pcp_assist_events_count,
        "start_commissar_events_count": start_commissar_events_count,
    })


@staff_member_required
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
        return render(request, "error.html", {"message": "Závod nebyl nalezen."})

    if event.ccf_uploaded:
        return render(request, "error.html", {
            "message": "Výsledky už byly odeslány.",
            "detail": f"Závod {event.name} byl již odeslán {event.ccf_created.strftime('%d.%m.%Y %H:%M:%S')}.",
        })

    token = get_api_token()
    if not token:
        return render(request, "error.html", {"message": "Nepodařilo se získat token pro přihlášení k API ČSC."})

    results = Result.objects.filter(event=event).select_related("rider__club")
    payload = []

    for res in results:
        rider = Rider.objects.filter(uci_id=res.rider).first()
        if not rider:
            logger.warning(f"Jezdec s UCI ID {res.rider} nenalezen, přeskakuji.")
            continue

        cruiser = not res.is_20 and not res.is_beginner
        category_code = resolve_api_category_code(
            rider=rider, is_20=res.is_20, is_24=cruiser, is_beginner=res.is_beginner
        )

        payload.append({
            "category": category_code,
            "rank": res.place,
            "bib": rider.plate_display,
            "uciid": str(rider.uci_id),
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
        response = requests.post(api_url, json=payload, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        with open(f"media/api-payloads/payload_event_{event.id}.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("Výsledky úspěšně odeslány do API ČSC pro event_id=%s", event.id)
    except Exception as e:
        logger.exception("Chyba při odesílání výsledků do API ČSC pro event_id=%s", event.id)
        return render(request, "error.html", {
            "message": "Nepodařilo se odeslat výsledky na API.", "detail": str(e)
        })

    event.ccf_created = now()
    event.ccf_uploaded = True
    event.save()

    return render(request, "event/results_sent.html", {"event": event, "sent_count": len(payload)})


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

    missing_competition_codes = [
        competition_code_field
        for _, _, competition_code_field in UCI_EXPORT_CATEGORY_CONFIG
        if not (getattr(event, competition_code_field, "") or "").strip()
    ]
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

    generated_files = []
    with tempfile.TemporaryDirectory(prefix="uci-export-") as tmp_dir:
        for slug, rider_class_name, competition_code_field in UCI_EXPORT_CATEGORY_CONFIG:
            competition_code = getattr(event, competition_code_field, "") or ""
            rows = _build_uci_export_rows(event, rider_class_name)

            export_name = (
                f"uci_results_{event.id}_"
                f"{_sanitize_export_filename(slug)}_"
                f"{_sanitize_export_filename(competition_code)}.xlsx"
            )
            destination_path = os.path.join(tmp_dir, export_name)
            _write_uci_export_workbook(
                template_path=UCI_EXPORT_TEMPLATE,
                destination_path=destination_path,
                competition_code=competition_code,
                event_code=event.uci_event_code,
                rows=rows,
            )
            logger.info(
                "UCI export kategorie vygenerován pro event_id=%s, slug=%s, rows=%s",
                event.id,
                slug,
                len(rows),
            )
            generated_files.append(destination_path)

        zip_name = (
            f"uci_results_event_{event.id}_{_sanitize_export_filename(event.name)}.zip"
        )
        zip_path = os.path.join(tmp_dir, zip_name)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in generated_files:
                zip_file.write(file_path, arcname=os.path.basename(file_path))

        with open(zip_path, "rb") as zip_handle:
            logger.info(
                "UCI export ZIP připraven pro event_id=%s, files=%s, zip_name=%s",
                event.id,
                len(generated_files),
                zip_name,
            )
            response = HttpResponse(zip_handle.read(), content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{zip_name}"'
            return response


@login_required(login_url="/login/")
@staff_member_required
def send_invoices(request, pk):
    """Rozesílání faktur klubům pro daný závod."""
    result = generate_event_invoices(pk)
    return render(request, "event/results_sent.html", {
        "event": Event.objects.get(pk=pk),
        "sent_count": len(result["sent"]),
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

    suffix = "with-amounts" if include_amounts else "without-amounts"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="prize-money-{event.id}-{suffix}-{timezone.now().strftime("%Y%m%d%H%M%S")}.pdf"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@login_required(login_url="/login/")
@staff_member_required
def import_event_stats(request, pk):
    """Stránka pro import statistických údajů závodu."""
    event = get_object_or_404(Event, pk=pk)

    if request.method == "POST":
        # Smazání všech souborů
        if "delete_all" in request.POST:
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
                            logger.error(f"Nepodařilo se smazat soubor {file_path}: {e}")
            
            RaceRun.objects.filter(event=event).delete()

            if deleted_count > 0:
                messages.success(request, _("Všechny statistiky byly smazány."))
            else:
                messages.info(request, _("Žádné soubory k smazání."))
            return redirect("event:import-stats", pk=pk)
        
        # Nahrávání souborů
        if request.FILES:
            count = 0
            for key in request.FILES:
                file = request.FILES[key]
                if file.name.lower().endswith(".html"):
                    _delete_uploaded_files_by_prefix("event_stats", str(pk), prefix=key)
                    # Prefix filename with key to identify category
                    original_name = os.path.basename(file.name)
                    file.name = f"{key}__{original_name}"
                    _save_uploaded_file(file, "event_stats", str(pk))
                    count += 1
            
            if count > 0:
                results_count = Result.objects.filter(event=event).count()
                imported_runs = RaceRunImportService().import_event_runs(event)
                messages.success(request, _("Úspěšně nahráno {count} souborů se statistikami.").format(count=count))
                messages.info(request, _("RaceRun aktualizován, zapsáno {count} jízd.").format(count=imported_runs))
                if results_count == 0:
                    messages.warning(
                        request,
                        _(
                            "Pro tento závod nejsou v databázi žádné výsledky (Result), takže statistické jízdy nešlo s nikým spárovat. Nejdřív nahraj výsledky závodu do Result a potom spusť import statistik znovu."
                        ),
                    )
                elif imported_runs == 0:
                    messages.warning(
                        request,
                        _(
                            "Statistické soubory se nahrály, ale nevznikl žádný RaceRun. Zkontroluj, že kategorie, jména a čísla v HTML odpovídají výsledkům uloženým v Result."
                        ),
                    )
            else:
                messages.warning(request, _("Nebyly nahrány žádné soubory (povoleny jsou pouze .html)."))
                
            return redirect("event:import-stats", pk=pk)

    # Načtení existujících souborů
    uploaded_files = []
    stats_dir = os.path.join(settings.MEDIA_ROOT, "event_stats", str(pk))
    
    category_map = {
        "motos": _("Motos - Startovní listina"),
        "motos_results": _("Motos - Výsledky"),
        "1_16": _("1/16 - Startovní listina"),
        "1_16_results": _("1/16 - Výsledky"),
        "1_8": _("1/8 - Startovní listina"),
        "1_8_results": _("1/8 - Výsledky"),
        "1_4": _("1/4 - Startovní listina"),
        "1_4_results": _("1/4 - Výsledky"),
        "1_2": _("1/2 - Startovní listina"),
        "1_2_results": _("1/2 - Výsledky"),
        "final": _("Finále - Startovní listina"),
        "final_results": _("Finále - Výsledky"),
    }

    if os.path.exists(stats_dir):
        for f in os.listdir(stats_dir):
            if os.path.isfile(os.path.join(stats_dir, f)):
                parts = f.split("__", 1)
                key = parts[0]
                original_name = parts[1] if len(parts) > 1 else f
                
                uploaded_files.append({
                    "filename": f,
                    "original_name": original_name,
                    "label": category_map.get(key, _("Neznámá kategorie")),
                    "url": f"{settings.MEDIA_URL}event_stats/{pk}/{f}",
                    "created": datetime.datetime.fromtimestamp(os.path.getctime(os.path.join(stats_dir, f)))
                })
    
    uploaded_files.sort(key=lambda x: x['label'])

    return render(request, "event/import-stats.html", {"event": event, "uploaded_files": uploaded_files})
