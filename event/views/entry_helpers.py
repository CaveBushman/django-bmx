import json
import logging
from datetime import date
from types import SimpleNamespace

import stripe
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from club.models import Club
from event.func import (
    generate_stripe_line,
    is_beginner,
    resolve_event_classes,
    resolve_event_fee,
    update_cart,
)
from event.models import Entry, EntryForeign, Event, SeasonSettings
from rider.models import ForeignRider, Rider


stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


def build_foreign_entry_summary(request):
    """Sestaví řádky zahraniční přihlášky z GET parametrů formuláře."""
    uci_ids = request.GET.getlist("uci_id[]")
    first_names = request.GET.getlist("first_name[]")
    last_names = request.GET.getlist("last_name[]")
    dates_of_birth = request.GET.getlist("dob[]")
    sexes = request.GET.getlist("sex[]")
    plates = request.GET.getlist("plate[]")
    nationalities = request.GET.getlist("nationality[]")
    transponder_20_list = request.GET.getlist("transponder_20[]")
    transponder_24_list = request.GET.getlist("transponder_24[]")
    category_20_flags = request.GET.getlist("category_20[]")
    category_24_flags = request.GET.getlist("category_24[]")
    elite_flags = request.GET.getlist("category_elite[]")

    customer_email = request.GET.get("customer_email", "").strip()
    rows = []
    total_rows = max(
        len(uci_ids),
        len(first_names),
        len(last_names),
        len(dates_of_birth),
        len(sexes),
        len(plates),
        len(nationalities),
        len(transponder_20_list),
        len(transponder_24_list),
    )

    for index in range(total_rows):
        row = {
            "uci_id": uci_ids[index] if index < len(uci_ids) else "",
            "first_name": first_names[index] if index < len(first_names) else "",
            "last_name": last_names[index] if index < len(last_names) else "",
            "date_of_birth": dates_of_birth[index] if index < len(dates_of_birth) else "",
            "sex": sexes[index] if index < len(sexes) else "",
            "plate": plates[index] if index < len(plates) else "",
            "nationality": nationalities[index] if index < len(nationalities) else "",
            "transponder_20": transponder_20_list[index] if index < len(transponder_20_list) else "",
            "transponder_24": transponder_24_list[index] if index < len(transponder_24_list) else "",
            "category_20": index < len(category_20_flags),
            "category_24": index < len(category_24_flags),
            "elite": index < len(elite_flags),
        }

        if any(
            [
                row["uci_id"],
                row["first_name"],
                row["last_name"],
                row["date_of_birth"],
                row["plate"],
                row["nationality"],
                row["transponder_20"],
                row["transponder_24"],
                row["category_20"],
                row["category_24"],
                row["elite"],
            ]
        ):
            rows.append(row)

    return {"customer_email": customer_email, "rows": rows}


def build_foreign_entry_summary_from_payload(request):
    payload = request.POST.get("summary_payload") or request.GET.get("summary_payload")
    if not payload:
        return None

    try:
        payload_data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if isinstance(payload_data, dict):
        rows = payload_data.get("rows", [])
        customer_email = payload_data.get("customer_email", "").strip()
    elif isinstance(payload_data, list):
        rows = payload_data
        customer_email = ""
    else:
        return None

    normalized_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized_rows.append(
            {
                "uci_id": row.get("uci_id", ""),
                "first_name": row.get("first_name", ""),
                "last_name": row.get("last_name", ""),
                "date_of_birth": row.get("date_of_birth", ""),
                "sex": row.get("sex", "Muž"),
                "plate": row.get("plate", ""),
                "nationality": row.get("nationality", ""),
                "transponder_20": row.get("transponder_20", ""),
                "transponder_24": row.get("transponder_24", ""),
                "category_20": bool(row.get("category_20")),
                "category_24": bool(row.get("category_24")),
                "elite": bool(row.get("elite")),
            }
        )

    return {
        "customer_email": customer_email,
        "rows": normalized_rows,
    }


def enrich_foreign_summary_rows(event, summary_rows):
    enriched_rows = []
    total_fee = 0
    sex_labels = {
        "Muž": "Male",
        "Žena": "Female",
        "Ostatní": "Other",
    }

    for row in summary_rows:
        event_category = ""
        entry_fee = 0

        rider_gender = row.get("sex") or "Muž"
        rider_is_elite = bool(row.get("elite"))
        rider_dob = row.get("date_of_birth")

        try:
            parsed_dob = date.fromisoformat(rider_dob) if rider_dob else date.today()
        except ValueError:
            parsed_dob = date.today()

        temp_rider = SimpleNamespace(
            gender=rider_gender,
            is_elite=rider_is_elite,
            date_of_birth=parsed_dob,
        )

        age = date.today().year - parsed_dob.year
        temp_rider.class_20 = ForeignRider.set_class_20(rider_gender, age, rider_is_elite)
        temp_rider.class_24 = ForeignRider.set_class_24(rider_gender, age)

        try:
            if row.get("category_24"):
                event_category = resolve_event_classes(event, temp_rider, is_20=False)
                entry_fee = resolve_event_fee(event, temp_rider, is_20=False)
            elif row.get("category_20"):
                event_category = resolve_event_classes(event, temp_rider, is_20=True)
                entry_fee = resolve_event_fee(event, temp_rider, is_20=True)
        except Exception:
            event_category = ""
            entry_fee = 0

        enriched_row = dict(row)
        enriched_row["sex_label"] = sex_labels.get(row.get("sex"), row.get("sex", ""))
        enriched_row["event_category"] = event_category
        enriched_row["entry_fee"] = entry_fee
        total_fee += entry_fee or 0
        enriched_rows.append(enriched_row)

    return enriched_rows, total_fee


def validate_foreign_summary_payload(payload):
    customer_email = (payload.get("customer_email") or "").strip()
    rows = payload.get("rows") or []

    if not customer_email or not rows:
        return False

    for row in rows:
        if not (row.get("first_name") or "").strip():
            return False
        if not (row.get("last_name") or "").strip():
            return False
        if not (row.get("uci_id") or "").strip():
            return False
        if not (row.get("date_of_birth") or "").strip():
            return False
        if not str(row.get("plate") or "").strip():
            return False
        if not (row.get("category_20") or row.get("category_24")):
            return False

    return True


def build_foreign_checkout_line_items(event, summary_rows):
    line_items = []
    for row in summary_rows:
        if not row.get("entry_fee"):
            continue

        category = row.get("event_category") or (
            '20"' if row.get("category_20") else '24"' if row.get("category_24") else "Entry"
        )
        rider_name = (
            f'{row.get("first_name", "").strip()} {row.get("last_name", "").strip()}'.strip()
            or row.get("uci_id")
            or "Foreign rider"
        )

        line_items.append(
            {
                "price_data": {
                    "currency": "czk",
                    "unit_amount": int(row["entry_fee"]) * 100,
                    "product_data": {
                        "name": rider_name,
                        "description": f"{event.name} - {category}",
                    },
                },
                "quantity": 1,
            }
        )

    return line_items


def save_foreign_entries(event, checkout_session, summary_rows, customer_email):
    for row in summary_rows:
        EntryForeign.objects.create(
            transaction_id=checkout_session.id,
            event=event,
            first_name=row.get("first_name", ""),
            last_name=row.get("last_name", ""),
            uci_id=row.get("uci_id", ""),
            date_of_birth=row.get("date_of_birth") or None,
            gender=row.get("sex", ""),
            nationality=(row.get("nationality") or "")[:3],
            club="",
            transponder=row.get("transponder_20") or row.get("transponder_24") or "",
            transponder_20=row.get("transponder_20", ""),
            transponder_24=row.get("transponder_24", ""),
            plate=str(row.get("plate", "")),
            is_20=bool(row.get("category_20")),
            is_24=bool(row.get("category_24")),
            is_elite=bool(row.get("elite")),
            class_20=row.get("event_category", "") if row.get("category_20") else "",
            class_24=row.get("event_category", "") if row.get("category_24") else "",
            fee_20=row.get("entry_fee", 0) if row.get("category_20") else 0,
            fee_24=row.get("entry_fee", 0) if row.get("category_24") else 0,
            customer_email=customer_email,
            payment_complete=False,
            checkout=False,
        )


def sync_paid_foreign_riders(event, session_id):
    paid_entries = EntryForeign.objects.filter(
        event=event,
        transaction_id=session_id,
        payment_complete=True,
    )

    for paid_entry in paid_entries:
        try:
            foreign_rider = ForeignRider.objects.get(uci_id=paid_entry.uci_id)
        except ForeignRider.DoesNotExist:
            foreign_rider = _create_foreign_rider_from_entry(paid_entry)
            if foreign_rider is None:
                continue
            continue

        _update_foreign_rider_from_entry(foreign_rider, paid_entry)


def _create_foreign_rider_from_entry(paid_entry):
    try:
        uci_id_value = int(str(paid_entry.uci_id).strip())
    except (TypeError, ValueError):
        return None

    try:
        plate_value = int(paid_entry.plate) if str(paid_entry.plate).strip() else 0
    except (TypeError, ValueError):
        plate_value = 0

    nationality_code = (paid_entry.nationality or "").strip()[:3]
    return ForeignRider.objects.create(
        uci_id=uci_id_value,
        first_name=paid_entry.first_name or "",
        last_name=paid_entry.last_name or "",
        date_of_birth=paid_entry.date_of_birth or date.today(),
        gender=paid_entry.gender or "Muž",
        nationality=nationality_code,
        state=nationality_code,
        plate=plate_value,
        transponder_20=paid_entry.transponder_20 or "",
        transponder_24=paid_entry.transponder_24 or "",
        is_20=paid_entry.is_20,
        is_24=paid_entry.is_24,
        is_elite=paid_entry.is_elite,
        class_20=paid_entry.class_20 or ForeignRider.CLASS_20[0][0],
        class_24=paid_entry.class_24 or ForeignRider.CLASS_24[0][0],
    )


def _update_foreign_rider_from_entry(foreign_rider, paid_entry):
    foreign_rider.first_name = paid_entry.first_name or foreign_rider.first_name
    foreign_rider.last_name = paid_entry.last_name or foreign_rider.last_name

    if paid_entry.date_of_birth:
        foreign_rider.date_of_birth = paid_entry.date_of_birth

    if paid_entry.gender:
        foreign_rider.gender = paid_entry.gender

    nationality_code = (paid_entry.nationality or "").strip()[:3]
    if nationality_code:
        foreign_rider.nationality = nationality_code
        foreign_rider.state = nationality_code

    try:
        if str(paid_entry.plate).strip():
            foreign_rider.plate = int(paid_entry.plate)
    except (TypeError, ValueError):
        pass

    foreign_rider.transponder_20 = paid_entry.transponder_20 or foreign_rider.transponder_20
    foreign_rider.transponder_24 = paid_entry.transponder_24 or foreign_rider.transponder_24
    foreign_rider.is_20 = paid_entry.is_20
    foreign_rider.is_24 = paid_entry.is_24
    foreign_rider.is_elite = paid_entry.is_elite
    foreign_rider.class_20 = paid_entry.class_20 or foreign_rider.class_20
    foreign_rider.class_24 = paid_entry.class_24 or foreign_rider.class_24
    foreign_rider.save()


def resolve_public_entry_category(entry):
    if getattr(entry, "is_beginner", False) and getattr(entry, "class_beginner", ""):
        return entry.class_beginner
    if getattr(entry, "is_20", False) and getattr(entry, "class_20", ""):
        return entry.class_20
    if getattr(entry, "is_24", False) and getattr(entry, "class_24", ""):
        return entry.class_24
    return ""


def build_public_entry_rows(entries, is_foreign=False):
    rows = []
    for entry in entries:
        category = resolve_public_entry_category(entry)
        if not category:
            continue

        if is_foreign:
            plate_value = getattr(entry, "plate", "")
            if plate_value in (None, ""):
                plate_display = "-"
            else:
                plate_display = str(plate_value)

            rows.append(
                SimpleNamespace(
                    is_foreign=True,
                    detail_url="",
                    photo_url="",
                    valid_licence=True,
                    last_name=(entry.last_name or "").upper(),
                    first_name=entry.first_name or "",
                    club=(entry.club or entry.nationality or "Foreign rider").upper(),
                    uci_id=entry.uci_id or "",
                    category=category,
                    plate=plate_display,
                )
            )
            continue

        rider = entry.rider
        photo_url = ""
        if rider and getattr(rider, "photo", None):
            try:
                photo_url = rider.photo.url
            except Exception:
                photo_url = ""

        rider_plate_value = getattr(rider, "plate", "") if rider else ""
        if rider_plate_value in (None, ""):
            rider_plate_display = "-"
        else:
            rider_plate_display = str(rider_plate_value)

        rows.append(
            SimpleNamespace(
                is_foreign=False,
                detail_url=(
                    reverse("rider:detail", args=[rider.uci_id])
                    if rider and getattr(rider, "uci_id", "")
                    else ""
                ),
                photo_url=photo_url,
                valid_licence=bool(getattr(rider, "valid_licence", False)),
                last_name=(getattr(rider, "last_name", "") or "").upper(),
                first_name=getattr(rider, "first_name", "") or "",
                club=(str(getattr(rider, "club", "")) or "").upper(),
                uci_id=getattr(rider, "uci_id", "") or "",
                category=category,
                plate=rider_plate_display,
            )
        )

    return rows


def replace_pending_entry(*, request, event, rider, category_flags, class_fields, fee_fields):
    """Nahradí starou nezaplacenou rezervaci novou pro stejný závod/jezdce/kategorii."""
    paid_entry_exists = Entry.objects.filter(
        rider=rider,
        event=event,
        payment_complete=True,
        **category_flags,
    ).exists()
    if paid_entry_exists:
        return

    Entry.objects.filter(
        rider=rider,
        event=event,
        payment_complete=False,
        **category_flags,
    ).delete()

    Entry.objects.create(
        user_id=request.user.id,
        event=event,
        rider=rider,
        **category_flags,
        **class_fields,
        **fee_fields,
    )


def get_active_riders():
    """Vrátí cacheovaný seznam aktivních schválených jezdců s platnou licencí."""
    riders = cache.get("active_riders")
    if riders is None:
        riders = list(
            Rider.objects.filter(is_active=True, is_approved=True)
            .filter(Q(valid_licence=True) | Q(fix_valid_licence=True))
            .prefetch_related("entry_set")
        )
        cache.set("active_riders", riders, timeout=600)
    return riders


def is_event_open_for_entries(event):
    return not event.canceled and event.reg_open and event.reg_open_to >= timezone.now()


def resolve_event_beginner_support(event):
    season = SeasonSettings.objects.filter(year=date.today().year).first()
    return event.is_beginners_event() and (season.beginners_allowed if season is not None else True)


def split_selected_riders(request):
    selected_beginner = set(request.POST.getlist("checkbox_beginner"))
    selected_20 = set(request.POST.getlist("checkbox_20"))
    selected_24 = set(request.POST.getlist("checkbox_24"))

    selected_uci_ids = {
        int(value)
        for value in selected_beginner.union(selected_20).union(selected_24)
        if value.isdigit()
    }
    selected_riders = Rider.objects.filter(uci_id__in=selected_uci_ids)

    riders_beginner, riders_20, riders_24 = [], [], []
    for rider in selected_riders:
        uci_str = str(rider.uci_id)
        if uci_str in selected_beginner:
            riders_beginner.append(rider)
        if uci_str in selected_20:
            riders_20.append(rider)
        if uci_str in selected_24:
            riders_24.append(rider)

    return riders_beginner, riders_20, riders_24


def calculate_selected_fee(event, riders_beginner, riders_20, riders_24):
    total_fee = 0
    for rider in riders_beginner:
        total_fee += resolve_event_fee(event, rider, is_20=True, is_beginner=True)
    for rider in riders_20:
        total_fee += resolve_event_fee(event, rider, is_20=True)
    for rider in riders_24:
        total_fee += resolve_event_fee(event, rider, is_20=False)
    return total_fee


def store_selected_entries(request, event, riders_beginner, riders_20, riders_24):
    for rider in riders_beginner:
        replace_pending_entry(
            request=request,
            event=event,
            rider=rider,
            category_flags={"is_beginner": True, "is_20": False, "is_24": False},
            class_fields={
                "class_beginner": resolve_event_classes(event, rider, is_20=True, is_beginner=True),
            },
            fee_fields={
                "fee_beginner": resolve_event_fee(event, rider, is_20=True, is_beginner=True),
            },
        )

    for rider in riders_20:
        replace_pending_entry(
            request=request,
            event=event,
            rider=rider,
            category_flags={"is_20": True, "is_beginner": False, "is_24": False},
            class_fields={
                "class_20": resolve_event_classes(event, rider, is_20=True),
            },
            fee_fields={
                "fee_20": resolve_event_fee(event, rider, is_20=True),
            },
        )

    for rider in riders_24:
        replace_pending_entry(
            request=request,
            event=event,
            rider=rider,
            category_flags={"is_24": True, "is_20": False, "is_beginner": False},
            class_fields={
                "class_24": resolve_event_classes(event, rider, is_20=False),
            },
            fee_fields={
                "fee_24": resolve_event_fee(event, rider, is_20=False),
            },
        )


def annotate_riders_for_event(event, riders, beginners_enabled):
    registered = Entry.objects.filter(event=event, payment_complete=True)
    registered_map = {entry.rider_id: entry for entry in registered}

    for rider in riders:
        if beginners_enabled and is_beginner(rider):
            rider.is_beginner = True
            rider.class_beginner = resolve_event_classes(event, rider, is_20=True, is_beginner=True)
        rider.class_20 = resolve_event_classes(event, rider, is_20=True)
        rider.class_24 = resolve_event_classes(event, rider, is_20=False)
        if rider.is_elite:
            rider.class_24 = "NELZE PŘIHLÁSIT"

        entry = registered_map.get(rider.pk)
        rider.is_registered_beginner = bool(entry and entry.is_beginner)
        rider.is_registered_20 = bool(entry and entry.is_20)
        rider.is_registered_24 = bool(entry and entry.is_24)


def load_checkout_session_payload(request):
    event_payload = json.loads(request.session["event"])
    event = Event.objects.get(id=event_payload["event"])
    riders_beginner = json.loads(request.session["riders_beginner"])
    riders_20 = json.loads(request.session["riders_20"])
    riders_24 = json.loads(request.session["riders_24"])
    return event, riders_beginner, riders_20, riders_24


def build_checkout_line_items(event, riders_beginner, riders_20, riders_24):
    line_items = []
    for rider_data in riders_beginner:
        rider = Rider.objects.get(uci_id=rider_data["fields"]["uci_id"])
        line_items += generate_stripe_line(event, rider, is_20=True, is_beginner=True)
    for rider_data in riders_20:
        rider = Rider.objects.get(uci_id=rider_data["fields"]["uci_id"])
        line_items += generate_stripe_line(event, rider, is_20=True)
    for rider_data in riders_24:
        rider = Rider.objects.get(uci_id=rider_data["fields"]["uci_id"])
        line_items += generate_stripe_line(event, rider, is_20=False)
    return line_items


def create_checkout_entries(event, checkout_session, rider_payloads, *, is_beginner=False, is_20=False, is_24=False):
    for rider_data in rider_payloads:
        rider = Rider.objects.get(uci_id=rider_data["fields"]["uci_id"])
        Entry.objects.create(
            transaction_id=checkout_session.id,
            event=event,
            rider=rider,
            is_beginner=is_beginner,
            is_20=is_20,
            is_24=is_24,
            class_beginner=resolve_event_classes(event, rider, is_20=True, is_beginner=True) if is_beginner else "",
            class_20=resolve_event_classes(event, rider, is_20=True) if is_20 else "",
            class_24=resolve_event_classes(event, rider, is_20=False) if is_24 else "",
            fee_beginner=resolve_event_fee(event, rider, is_20=True, is_beginner=True) if is_beginner else 0,
            fee_20=resolve_event_fee(event, rider, is_20=True) if is_20 else 0,
            fee_24=resolve_event_fee(event, rider, is_20=False) if is_24 else 0,
        )


def load_foreign_rider_response(request):
    """AJAX endpoint — vrátí data zahraničního jezdce podle UCI ID."""
    uci_id = request.GET.get("uci_id", None)
    if uci_id:
        digits = "".join(filter(str.isdigit, uci_id))
        if not digits:
            return JsonResponse(
                {"error": "Rider not found", "manual_entry": True},
                status=200,
            )
        uci_id = int(digits)
        try:
            rider = ForeignRider.objects.get(uci_id=uci_id)
            nationality_code = rider.nationality or rider.state or ""
            return JsonResponse(
                {
                    "first_name": rider.first_name,
                    "last_name": rider.last_name,
                    "date_of_birth": rider.date_of_birth,
                    "sex": rider.gender,
                    "plate": rider.plate,
                    "transponder_20": rider.transponder_20,
                    "transponder_24": rider.transponder_24,
                    "nationality": nationality_code,
                    "manual_entry": False,
                }
            )
        except ForeignRider.DoesNotExist:
            return JsonResponse(
                {"error": "Rider not found", "manual_entry": True},
                status=200,
            )
    return JsonResponse({"error": "UCI ID is required"}, status=400)


def collect_fees_by_club(event):
    """Přehled startovného na závodě rozdělený po klubech."""
    entries = Entry.objects.filter(event=event.pk, checkout=False)
    clubs = Club.objects.filter(is_active=True).order_by("team_name")

    club_in_event = []
    for club in clubs:
        fee = sum(
            entry.fee_20 + entry.fee_24 + entry.fee_beginner
            for entry in entries
            if club == entry.rider.club
        )
        if fee > 0:
            club.fee = fee
            club_in_event.append(club)

    return club_in_event
