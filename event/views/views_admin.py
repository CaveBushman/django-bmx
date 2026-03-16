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
import os
from collections import Counter
import pandas as pd
import requests
from datetime import date
from types import SimpleNamespace
from django.shortcuts import get_object_or_404, render, reverse, HttpResponseRedirect
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.cache import cache_control
from event.models import Event, Entry, EntryForeign, Result, RaceRun
from rider.models import Rider
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
from ranking.ranking import SetRanking
from rider.rider import get_api_token, generate_insurance_file, resolve_api_category_code
from finance.invoices import generate_event_invoices
from openpyxl import Workbook, load_workbook
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


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
    filename = storage.save(uploaded_file.name, uploaded_file)
    return storage, filename, os.path.join(relative_dir, filename)


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
    SetRanking().start()
    logger.info(f"BEM výsledky nahrány pro závod {event.id}")
    return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": pk}))


def _handle_delete_xls(request, event, pk):
    """Smaže XLS výsledky a přepočítá ranking."""
    Result.objects.filter(event=pk).delete()
    SetRanking().start()
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
        world_plate = ("W" + str(rider.plate_champ_20)) if rider.plate_champ_20 else rider.plate
        ws.cell(row, 24, world_plate)
        ws.cell(row, 25, rider.plate)
    else:
        ws.cell(row, 21, resolve_event_classes(event, rider, is_20=False))
        world_plate = ("W" + str(rider.plate_champ_24)) if rider.plate_champ_24 else str(rider.plate)
        ws.cell(row, 24, rider.plate)
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
            ws.cell(x, 24, rider.plate_champ_20 or rider.plate)
            ws.cell(x, 25, rider.plate_champ_24 or rider.plate)
        x += 1

    wb.save(file_name)
    event.bem_riders_list = file_name
    event.bem_riders_created = timezone.now()
    event.save()
    logger.info(f"BEM seznam jezdců vygenerován: {file_name}")


def _handle_rem_entries(request, event):
    """Vygeneruje REM soubor s online přihláškami (přihlášení jezdci)."""
    all_entries = REMRiders()
    all_entries.event = event
    all_entries.create_entries_list()
    logger.info(f"REM přihlášky vygenerovány pro závod {event.id}")


def _handle_rem_riders(request, event):
    """Vygeneruje REM soubor se seznamem všech aktivních jezdců."""
    all_riders = REMRiders()
    all_riders.event = event
    all_riders.create_all_riders_list()
    logger.info(f"REM seznam jezdců vygenerován pro závod {event.id}")


def _handle_upload_txt(request, event, pk):
    """Nahraje TSV výsledky z REM a zapíše detailní RaceRun záznamy (MOTO, finále)."""
    if "result-file-txt" not in request.FILES:
        messages.error(request, "Musíš vybrat soubor s výsledky závodu")
        return HttpResponseRedirect(reverse("event:event-admin", kwargs={"pk": pk}))

    result_file = request.FILES["result-file-txt"]
    storage, filename, relative_path = _save_uploaded_file(result_file, "rem_results")

    # Import výsledků do DB a přepočet rankingu na pozadí
    results = SetResults()
    results.setEvent(pk)
    results.setFile(filename)
    results.start()

    # Zápis detailních jízdních dat do RaceRun
    df = pd.read_csv(storage.path(filename), sep="\t")
    _save_race_runs(df, event)

    event.rem_results = relative_path
    event.save(update_fields=["rem_results"])

    logger.info(f"REM výsledky nahrány pro závod {event.id}")
    return None  # Pokračuj na shrnutí


def _save_race_runs(df, event):
    """Projde TSV DataFrame a zapíše MOTO + finálové záznamy do RaceRun modelu."""
    for _, row in df.iterrows():
        plate = row.get("PLATE")
        if pd.isna(plate):
            continue
        plate_digits = "".join(filter(str.isdigit, str(plate)))
        if not plate_digits:
            continue

        result = Result.objects.filter(event=event, rider=int(plate_digits)).first()
        if not result:
            continue

        # MOTO jízdy (až 9 kol)
        for i in range(1, 10):
            if not pd.isna(row.get(f"MOTO{i}_PLACE")):
                RaceRun.objects.get_or_create(
                    result=result, round_type="MOTO", round_number=i,
                    defaults=dict(
                        gate=row.get(f"MOTO{i}_GATE"), lane=row.get(f"MOTO{i}_LANE"),
                        place=row.get(f"MOTO{i}_PLACE"), race_points=row.get(f"MOTO{i}_RACE_POINTS"),
                        moto_points=row.get(f"MOTO{i}_MOTO_POINTS"), finish_time=row.get(f"MOTO{i}_TIME"),
                        hill_time=None, split_1=None, split_2=None, split_3=None, split_4=None,
                    )
                )

        # Finálové a eliminační kola
        for phase in ["FINAL", "F2", "F4", "F8", "F16", "F32", "F64", "F128"]:
            if not pd.isna(row.get(f"{phase}_PLACE")):
                RaceRun.objects.get_or_create(
                    result=result, round_type=phase,
                    defaults=dict(
                        round_number=None,
                        gate=row.get(f"{phase}_GATE"), lane=row.get(f"{phase}_LANE"),
                        place=row.get(f"{phase}_PLACE"), race_points=row.get(f"{phase}_RACE_POINTS"),
                        moto_points=row.get(f"{phase}_MOTO_POINTS"), finish_time=row.get(f"{phase}_TIME"),
                        hill_time=None, split_1=None, split_2=None, split_3=None, split_4=None,
                    )
                )


def _handle_delete_txt(request, event, pk):
    """Smaže REM výsledky a přepočítá ranking."""
    Result.objects.filter(event=pk).delete()
    event.ccf_uploaded = False
    event.ccf_created = None
    event.save()
    SetRanking().start()
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
        _handle_bem_entries(request, event)

    elif "btn-riders-list" in request.POST:
        _handle_bem_riders(request, event)

    elif "btn-rem-file" in request.POST:
        _handle_rem_entries(request, event)

    elif "btn-rem-riders-list" in request.POST:
        _handle_rem_riders(request, event)

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


@staff_member_required
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
        .select_related("pcp", "pcp_assist", "start_commissar")
        .order_by("date", "name")
    )

    return render(request, "event/commissar-assignments.html", {
        "events": events,
        "selected_year": int(selected_year),
        "year_options": year_options,
    })


@staff_member_required
def commissar_statistics_view(request):
    """Admin-only statistika nasazení rozhodčích podle roku."""
    year_options = list(_get_event_year_options())
    selected_year = _resolve_selected_year(request.GET.get("year"), year_options)

    commissars = (
        Commissar.objects.filter(is_active=True)
        .annotate(
            pcp_count=Count("PCP", filter=Q(PCP__date__year=selected_year), distinct=True),
            pcp_assist_count=Count(
                "PCP_asist",
                filter=Q(PCP_asist__date__year=selected_year),
                distinct=True,
            ),
            start_commissar_count=Count(
                "start_commissar_events",
                filter=Q(start_commissar_events__date__year=selected_year),
                distinct=True,
            ),
        )
        .order_by("last_name", "first_name")
    )

    return render(request, "event/commissar-statistics.html", {
        "commissars": commissars,
        "selected_year": int(selected_year),
        "year_options": year_options,
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
            "bib": rider.plate,
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
        response = requests.post(api_url, json=payload, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        with open(f"media/api-payloads/payload_event_{event.id}.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return render(request, "error.html", {
            "message": "Nepodařilo se odeslat výsledky na API.", "detail": str(e)
        })

    event.ccf_created = now()
    event.ccf_uploaded = True
    event.save()

    return render(request, "event/results_sent.html", {"event": event, "sent_count": len(payload)})


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
    """PDF seznam prize money — TODO."""
    pass
