import json
import logging
from datetime import date
from types import SimpleNamespace

import stripe
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse

from club.models import Club
from event.func import (
    generate_stripe_line,
    is_beginner,
    is_registration_open,
    resolve_event_classes,
    resolve_event_fee,
)
from event.models import Entry, EntryForeign, Event, SeasonSettings, normalize_uci_id
from rider.models import ForeignRider, Rider
from rider.plates import display_plate, legacy_plate_int, normalize_plate_value


stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


def _normalize_foreign_category_flags(row):
    challenge = bool(row.get("challenge"))
    championship = bool(row.get("championship"))
    cruiser = bool(row.get("cruiser"))

    # Backward compatibility for older payloads/form posts.
    legacy_20 = bool(row.get("category_20"))
    legacy_24 = bool(row.get("category_24"))
    legacy_elite = bool(row.get("elite"))

    if legacy_elite:
        championship = True
    elif legacy_20:
        challenge = True

    if legacy_24:
        cruiser = True

    return {
        "challenge": challenge,
        "championship": championship,
        "cruiser": cruiser,
        "category_20": challenge or championship,
        "category_24": cruiser,
        "elite": championship,
    }


def _get_rider_event_snapshot(rider):
    snapshot = getattr(rider, "_event_entry_snapshot", None)
    if snapshot is None:
        snapshot = {}
        rider._event_entry_snapshot = snapshot
    return snapshot


def _resolve_rider_event_data(event, rider, *, beginners_enabled=False):
    """Spočítá a cacheuje category/fee data pro rider+event v rámci requestu."""
    event_key = event.pk or id(event)
    snapshot = _get_rider_event_snapshot(rider)
    cache_key = (event_key, bool(beginners_enabled))
    cached = snapshot.get(cache_key)
    if cached is not None:
        return cached

    data = {
        "is_beginner": bool(beginners_enabled and is_beginner(rider)),
        "class_beginner": "",
        "class_20": resolve_event_classes(event, rider, is_20=True),
        "class_24": resolve_event_classes(event, rider, is_20=False),
        "fee_beginner": 0,
        "fee_20": resolve_event_fee(event, rider, is_20=True),
        "fee_24": resolve_event_fee(event, rider, is_20=False),
    }

    if data["is_beginner"]:
        data["class_beginner"] = resolve_event_classes(event, rider, is_20=True, is_beginner=True)
        data["fee_beginner"] = resolve_event_fee(event, rider, is_20=True, is_beginner=True)

    if rider.is_elite:
        data["class_24"] = "NELZE PŘIHLÁSIT"

    data["allow_beginner"] = data["is_beginner"] and event.is_beginners_event()
    data["allow_20"] = (
        not (
            event.type_for_ranking == "Mistrovství ČR jednotlivců"
            and not rider.is_qualify_to_cn_20
        )
        and data["class_20"] not in {"", "NENÍ VYPSÁNO", "NELZE PŘIHLÁSIT"}
    )
    data["allow_24"] = (
        not rider.is_elite
        and not (
            event.type_for_ranking == "Mistrovství ČR jednotlivců"
            and not rider.is_qualify_to_cn_24
        )
        and data["class_24"] not in {"", "NENÍ VYPSÁNO", "NELZE PŘIHLÁSIT"}
    )

    snapshot[cache_key] = data
    return data


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
    challenge_flags = request.GET.getlist("challenge[]")
    championship_flags = request.GET.getlist("championship[]")
    cruiser_flags = request.GET.getlist("cruiser[]")

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
        category_flags = _normalize_foreign_category_flags(
            {
                "challenge": index < len(challenge_flags),
                "championship": index < len(championship_flags),
                "cruiser": index < len(cruiser_flags),
            }
        )

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
            **category_flags,
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
                row["challenge"],
                row["championship"],
                row["cruiser"],
            ]
        ):
            rows.append(row)

    return {"customer_email": customer_email, "rows": rows}


def build_foreign_entry_summary_from_payload(request):
    payload = (
        request.POST.get("summary_payload")
        or request.GET.get("summary_payload")
        or request.session.get("foreign_summary_payload", "")
    )
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
        category_flags = _normalize_foreign_category_flags(row)
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
                **category_flags,
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
        rider_gender = row.get("sex") or "Muž"
        rider_dob = row.get("date_of_birth")
        category_flags = _normalize_foreign_category_flags(row)

        try:
            parsed_dob = date.fromisoformat(rider_dob) if rider_dob else date.today()
        except ValueError:
            parsed_dob = date.today()

        age = date.today().year - parsed_dob.year
        class_20 = ""
        class_24 = ""
        fee_20 = 0
        fee_24 = 0
        selected_labels = []

        if category_flags["challenge"] or category_flags["championship"]:
            rider_20 = SimpleNamespace(
                gender=rider_gender,
                is_elite=category_flags["championship"],
                date_of_birth=parsed_dob,
            )
            rider_20.class_20 = ForeignRider.set_class_20(
                rider_gender,
                age,
                category_flags["championship"],
            )
            rider_20.class_24 = ForeignRider.set_class_24(rider_gender, age)
            try:
                class_20 = resolve_event_classes(event, rider_20, is_20=True)
                fee_20 = resolve_event_fee(event, rider_20, is_20=True)
            except Exception:
                class_20 = ""
                fee_20 = 0
            selected_labels.append("Championship" if category_flags["championship"] else "Challenge")

        if category_flags["cruiser"]:
            rider_24 = SimpleNamespace(
                gender=rider_gender,
                is_elite=False,
                date_of_birth=parsed_dob,
            )
            rider_24.class_20 = ForeignRider.set_class_20(rider_gender, age, False)
            rider_24.class_24 = ForeignRider.set_class_24(rider_gender, age)
            try:
                class_24 = resolve_event_classes(event, rider_24, is_20=False)
                fee_24 = resolve_event_fee(event, rider_24, is_20=False)
            except Exception:
                class_24 = ""
                fee_24 = 0
            selected_labels.append("Cruiser")

        enriched_row = dict(row)
        enriched_row.update(category_flags)
        enriched_row["sex_label"] = sex_labels.get(row.get("sex"), row.get("sex", ""))
        enriched_row["class_20"] = class_20
        enriched_row["class_24"] = class_24
        enriched_row["event_category"] = " / ".join(filter(None, [class_20, class_24]))
        enriched_row["entry_fee"] = (fee_20 or 0) + (fee_24 or 0)
        enriched_row["fee_20"] = fee_20
        enriched_row["fee_24"] = fee_24
        enriched_row["selected_categories"] = selected_labels
        total_fee += enriched_row["entry_fee"]
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
        category_flags = _normalize_foreign_category_flags(row)

        if category_flags["championship"] and (category_flags["challenge"] or category_flags["cruiser"]):
            return False
        if not (category_flags["challenge"] or category_flags["championship"] or category_flags["cruiser"]):
            return False

    return True


def build_foreign_checkout_line_items(event, summary_rows):
    line_items = []
    for row in summary_rows:
        if not row.get("entry_fee"):
            continue

        rider_name = (
            f'{row.get("first_name", "").strip()} {row.get("last_name", "").strip()}'.strip()
            or row.get("uci_id")
            or "Foreign rider"
        )
        if row.get("fee_20"):
            category_20_label = row.get("class_20") or (
                "Championship" if row.get("championship") else "Challenge"
            )
            line_items.append(
                {
                    "price_data": {
                        "currency": "czk",
                        "unit_amount": int(row["fee_20"]) * 100,
                        "product_data": {
                            "name": rider_name,
                            "description": f"{event.name} - {category_20_label}",
                        },
                    },
                    "quantity": 1,
                }
            )
        if row.get("fee_24"):
            category_24_label = row.get("class_24") or "Cruiser"
            line_items.append(
                {
                    "price_data": {
                        "currency": "czk",
                        "unit_amount": int(row["fee_24"]) * 100,
                        "product_data": {
                            "name": rider_name,
                            "description": f"{event.name} - {category_24_label}",
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
            is_20=bool(row.get("challenge") or row.get("championship") or row.get("category_20")),
            is_24=bool(row.get("cruiser") or row.get("category_24")),
            is_elite=bool(row.get("championship") or row.get("elite")),
            class_20=row.get("class_20", "") if (row.get("challenge") or row.get("championship") or row.get("category_20")) else "",
            class_24=row.get("class_24", "") if (row.get("cruiser") or row.get("category_24")) else "",
            fee_20=row.get("fee_20", 0) if (row.get("challenge") or row.get("championship") or row.get("category_20")) else 0,
            fee_24=row.get("fee_24", 0) if (row.get("cruiser") or row.get("category_24")) else 0,
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
        normalized_uci_id = normalize_uci_id(paid_entry.uci_id)
        if not normalized_uci_id:
            continue

        # Zkusit provázat s českým jezdcem (Čech se zahraniční licencí)
        try:
            uci_id_int = int(normalized_uci_id)
        except (TypeError, ValueError):
            uci_id_int = None

        if uci_id_int is not None and paid_entry.rider_id is None:
            czech_rider = Rider.objects.filter(uci_id=uci_id_int).first()
            if czech_rider is not None:
                EntryForeign.objects.filter(pk=paid_entry.pk).update(rider=czech_rider)
                paid_entry.rider = czech_rider
                logger.info(
                    "sync_paid_foreign_riders: EntryForeign pk=%s provázána s českým jezdcem pk=%s (%s %s)",
                    paid_entry.pk,
                    czech_rider.pk,
                    czech_rider.first_name,
                    czech_rider.last_name,
                )

        try:
            foreign_rider = ForeignRider.objects.get(uci_id=int(normalized_uci_id))
        except (ForeignRider.DoesNotExist, ValueError):
            foreign_rider = _create_foreign_rider_from_entry(paid_entry)
            if foreign_rider is None:
                continue

        _update_foreign_rider_from_entry(foreign_rider, paid_entry)


def _create_foreign_rider_from_entry(paid_entry):
    try:
        uci_id_value = int(normalize_uci_id(paid_entry.uci_id))
    except (TypeError, ValueError):
        return None

    normalized_plate = normalize_plate_value(paid_entry.plate)

    nationality_code = (paid_entry.nationality or "").strip()[:3]
    foreign_rider = ForeignRider.objects.create(
        uci_id=uci_id_value,
        first_name=paid_entry.first_name or "",
        last_name=paid_entry.last_name or "",
        date_of_birth=paid_entry.date_of_birth or date.today(),
        gender=paid_entry.gender or "Muž",
        nationality=nationality_code,
        state=nationality_code,
        plate=legacy_plate_int(normalized_plate),
        plate_text=normalized_plate,
        transponder_20=paid_entry.transponder_20 or "",
        transponder_24=paid_entry.transponder_24 or "",
        is_20=paid_entry.is_20,
        is_24=paid_entry.is_24,
        is_elite=paid_entry.is_elite,
        class_20=paid_entry.class_20 or ForeignRider.CLASS_20[0][0],
        class_24=paid_entry.class_24 or ForeignRider.CLASS_24[0][0],
    )
    explicit_updates = {}
    if paid_entry.class_20:
        explicit_updates["class_20"] = paid_entry.class_20
    if paid_entry.class_24:
        explicit_updates["class_24"] = paid_entry.class_24
    if explicit_updates:
        ForeignRider.objects.filter(pk=foreign_rider.pk).update(**explicit_updates)
        for field_name, field_value in explicit_updates.items():
            setattr(foreign_rider, field_name, field_value)
    return foreign_rider


def _update_foreign_rider_from_entry(foreign_rider, paid_entry):
    update_data = {
        "first_name": paid_entry.first_name or foreign_rider.first_name,
        "last_name": paid_entry.last_name or foreign_rider.last_name,
        "transponder_20": paid_entry.transponder_20 or foreign_rider.transponder_20,
        "transponder_24": paid_entry.transponder_24 or foreign_rider.transponder_24,
        "is_20": paid_entry.is_20,
        "is_24": paid_entry.is_24,
        "is_elite": paid_entry.is_elite,
        "class_20": paid_entry.class_20 or foreign_rider.class_20,
        "class_24": paid_entry.class_24 or foreign_rider.class_24,
    }

    if paid_entry.date_of_birth:
        update_data["date_of_birth"] = paid_entry.date_of_birth

    if paid_entry.gender:
        update_data["gender"] = paid_entry.gender

    nationality_code = (paid_entry.nationality or "").strip()[:3]
    if nationality_code:
        update_data["nationality"] = nationality_code
        update_data["state"] = nationality_code

    normalized_plate = normalize_plate_value(paid_entry.plate)
    if normalized_plate:
        update_data["plate_text"] = normalized_plate
        update_data["plate"] = legacy_plate_int(normalized_plate)

    ForeignRider.objects.filter(pk=foreign_rider.pk).update(**update_data)
    for field_name, field_value in update_data.items():
        setattr(foreign_rider, field_name, field_value)


def resolve_public_entry_categories(entry):
    categories = []
    if getattr(entry, "is_beginner", False) and getattr(entry, "class_beginner", ""):
        categories.append(entry.class_beginner)
    if getattr(entry, "is_20", False) and getattr(entry, "class_20", ""):
        categories.append(entry.class_20)
    if getattr(entry, "is_24", False) and getattr(entry, "class_24", ""):
        categories.append(entry.class_24)
    return categories


def build_public_entry_rows(entries, is_foreign=False):
    rows = []
    for entry in entries:
        categories = resolve_public_entry_categories(entry)
        if not categories:
            continue

        if is_foreign:
            czech_rider = getattr(entry, "rider", None)
            photo_url = ""
            detail_url = ""
            if czech_rider and getattr(czech_rider, "photo", None):
                try:
                    photo_url = czech_rider.photo.url
                except Exception:
                    photo_url = ""
            if czech_rider and getattr(czech_rider, "uci_id", ""):
                try:
                    detail_url = reverse("rider:detail", args=[czech_rider.uci_id])
                except Exception:
                    detail_url = ""
            for category in categories:
                rows.append(
                    SimpleNamespace(
                        is_foreign=True,
                        detail_url=detail_url,
                        photo_url=photo_url,
                        valid_licence=True,
                        last_name=(entry.last_name or "").upper(),
                        first_name=entry.first_name or "",
                        club=(entry.club or entry.nationality or "Foreign rider").upper(),
                        uci_id=entry.uci_id or "",
                        category=category,
                        plate=display_plate(getattr(entry, "plate", ""), fallback="-"),
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

        for category in categories:
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
                    plate=display_plate(
                        getattr(rider, "plate_text", "") if rider else "",
                        getattr(rider, "plate", "") if rider else "",
                        fallback="-",
                    ),
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
        )
        cache.set("active_riders", riders, timeout=600)
    return riders


def is_event_open_for_entries(event):
    return not event.canceled and is_registration_open(event)


def resolve_event_beginner_support(event):
    season = SeasonSettings.objects.filter(year=date.today().year).first()
    return event.is_beginners_event() and (season.beginners_allowed if season is not None else True)


def _is_rider_allowed_for_event_category(event, rider, *, is_20=False, is_24=False, is_beginner=False):
    data = _resolve_rider_event_data(event, rider, beginners_enabled=True)
    if is_beginner:
        return data["allow_beginner"]

    if is_20:
        return data["allow_20"]

    if is_24:
        return data["allow_24"]

    return False


def split_selected_riders(request, event):
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
        if uci_str in selected_beginner and _is_rider_allowed_for_event_category(event, rider, is_beginner=True):
            riders_beginner.append(rider)
        if uci_str in selected_20 and _is_rider_allowed_for_event_category(event, rider, is_20=True):
            riders_20.append(rider)
        if uci_str in selected_24 and _is_rider_allowed_for_event_category(event, rider, is_24=True):
            riders_24.append(rider)

    return riders_beginner, riders_20, riders_24


def calculate_selected_fee(event, riders_beginner, riders_20, riders_24):
    total_fee = 0
    for rider in riders_beginner:
        total_fee += _resolve_rider_event_data(event, rider, beginners_enabled=True)["fee_beginner"]
    for rider in riders_20:
        total_fee += _resolve_rider_event_data(event, rider, beginners_enabled=True)["fee_20"]
    for rider in riders_24:
        total_fee += _resolve_rider_event_data(event, rider, beginners_enabled=True)["fee_24"]
    return total_fee


def build_event_category_participants(event):
    category_participants = {}

    def append_participant(category_name, *, plate_value, first_name, last_name):
        if not category_name:
            return
        participants = category_participants.setdefault(category_name, [])
        participants.append(
            {
                "plate": plate_value,
                "first_name": first_name or "",
                "last_name": last_name or "",
            }
        )

    paid_entries = (
        Entry.objects.filter(event=event, payment_complete=True, checkout=False)
        .select_related("rider")
    )
    for entry in paid_entries:
        rider = getattr(entry, "rider", None)
        if rider is None:
            continue
        participant_kwargs = {
            "plate_value": display_plate(getattr(rider, "plate_text", ""), getattr(rider, "plate", None)),
            "first_name": getattr(rider, "first_name", ""),
            "last_name": getattr(rider, "last_name", ""),
        }
        if getattr(entry, "is_beginner", False):
            append_participant(entry.class_beginner, **participant_kwargs)
        if getattr(entry, "is_20", False):
            append_participant(entry.class_20, **participant_kwargs)
        if getattr(entry, "is_24", False):
            append_participant(entry.class_24, **participant_kwargs)

    foreign_entries = EntryForeign.objects.filter(event=event, payment_complete=True, checkout=False)
    for entry in foreign_entries:
        participant_kwargs = {
            "plate_value": display_plate(getattr(entry, "plate", "")),
            "first_name": getattr(entry, "first_name", ""),
            "last_name": getattr(entry, "last_name", ""),
        }
        if getattr(entry, "is_20", False):
            append_participant(entry.class_20, **participant_kwargs)
        if getattr(entry, "is_24", False):
            append_participant(entry.class_24, **participant_kwargs)

    for category_name, participants in category_participants.items():
        participants.sort(
            key=lambda item: (
                item["last_name"].upper(),
                item["first_name"].upper(),
                item["plate"],
            )
        )

    return category_participants


def store_selected_entries(request, event, riders_beginner, riders_20, riders_24):
    for rider in riders_beginner:
        rider_data = _resolve_rider_event_data(event, rider, beginners_enabled=True)
        replace_pending_entry(
            request=request,
            event=event,
            rider=rider,
            category_flags={"is_beginner": True, "is_20": False, "is_24": False},
            class_fields={
                "class_beginner": rider_data["class_beginner"],
            },
            fee_fields={
                "fee_beginner": rider_data["fee_beginner"],
            },
        )

    for rider in riders_20:
        rider_data = _resolve_rider_event_data(event, rider, beginners_enabled=True)
        replace_pending_entry(
            request=request,
            event=event,
            rider=rider,
            category_flags={"is_20": True, "is_beginner": False, "is_24": False},
            class_fields={
                "class_20": rider_data["class_20"],
            },
            fee_fields={
                "fee_20": rider_data["fee_20"],
            },
        )

    for rider in riders_24:
        rider_data = _resolve_rider_event_data(event, rider, beginners_enabled=True)
        replace_pending_entry(
            request=request,
            event=event,
            rider=rider,
            category_flags={"is_24": True, "is_20": False, "is_beginner": False},
            class_fields={
                "class_24": rider_data["class_24"],
            },
            fee_fields={
                "fee_24": rider_data["fee_24"],
            },
        )


def annotate_riders_for_event(event, riders, beginners_enabled):
    registered = Entry.objects.filter(event=event, payment_complete=True).only(
        "rider_id", "is_beginner", "is_20", "is_24"
    )
    registered_map = {}
    for entry in registered:
        rider_flags = registered_map.setdefault(
            entry.rider_id,
            {"is_beginner": False, "is_20": False, "is_24": False},
        )
        rider_flags["is_beginner"] = rider_flags["is_beginner"] or bool(entry.is_beginner)
        rider_flags["is_20"] = rider_flags["is_20"] or bool(entry.is_20)
        rider_flags["is_24"] = rider_flags["is_24"] or bool(entry.is_24)

    category_participants = build_event_category_participants(event)

    for rider in riders:
        rider_data = _resolve_rider_event_data(event, rider, beginners_enabled=beginners_enabled)
        rider.is_beginner = rider_data["is_beginner"]
        rider.class_beginner = rider_data["class_beginner"]
        rider.class_20 = rider_data["class_20"]
        rider.class_24 = rider_data["class_24"]

        entry_flags = registered_map.get(rider.pk, {})
        rider.is_registered_beginner = bool(entry_flags.get("is_beginner"))
        rider.is_registered_20 = bool(entry_flags.get("is_20"))
        rider.is_registered_24 = bool(entry_flags.get("is_24"))

        for field_name in ("class_beginner", "class_20", "class_24"):
            category_name = getattr(rider, field_name, "")
            participants = category_participants.get(category_name, [])
            setattr(rider, f"{field_name}_participants", participants)
            setattr(rider, f"{field_name}_participant_count", len(participants))


def load_checkout_session_payload(request):
    event_payload = json.loads(request.session["event"])
    event = Event.objects.select_related("classes_and_fees_like").get(id=event_payload["event"])
    riders_beginner = json.loads(request.session["riders_beginner"])
    riders_20 = json.loads(request.session["riders_20"])
    riders_24 = json.loads(request.session["riders_24"])
    return event, riders_beginner, riders_20, riders_24


def _map_riders_from_payloads(*payload_groups):
    uci_ids = []
    for payload_group in payload_groups:
        for rider_data in payload_group:
            uci_id = rider_data["fields"]["uci_id"]
            if uci_id is not None:
                uci_ids.append(uci_id)

    return Rider.objects.in_bulk(uci_ids, field_name="uci_id")


def hydrate_checkout_riders(event, rider_payloads, *, is_beginner=False, is_20=False, is_24=False):
    rider_map = _map_riders_from_payloads(rider_payloads)
    riders = []
    for rider_data in rider_payloads:
        rider = rider_map.get(rider_data["fields"]["uci_id"])
        if rider is None:
            continue
        event_data = _resolve_rider_event_data(event, rider, beginners_enabled=True)
        rider.is_beginner = is_beginner
        rider.is_20 = is_20
        rider.is_24 = is_24
        rider.class_beginner = event_data["class_beginner"]
        rider.class_20 = event_data["class_20"]
        rider.class_24 = event_data["class_24"]
        rider.fee_beginner = event_data["fee_beginner"]
        rider.fee_20 = event_data["fee_20"]
        rider.fee_24 = event_data["fee_24"]
        riders.append(rider)
    return riders


def build_checkout_line_items(event, riders_beginner, riders_20, riders_24):
    line_items = []
    rider_map = _map_riders_from_payloads(riders_beginner, riders_20, riders_24)
    for rider_data in riders_beginner:
        rider = rider_map[rider_data["fields"]["uci_id"]]
        line_items += generate_stripe_line(event, rider, is_20=True, is_beginner=True)
    for rider_data in riders_20:
        rider = rider_map[rider_data["fields"]["uci_id"]]
        line_items += generate_stripe_line(event, rider, is_20=True)
    for rider_data in riders_24:
        rider = rider_map[rider_data["fields"]["uci_id"]]
        line_items += generate_stripe_line(event, rider, is_20=False)
    return line_items


def create_checkout_entries(event, checkout_session, rider_payloads, *, is_beginner=False, is_20=False, is_24=False):
    rider_map = _map_riders_from_payloads(rider_payloads)
    for rider_data in rider_payloads:
        rider = rider_map[rider_data["fields"]["uci_id"]]
        rider_event_data = _resolve_rider_event_data(event, rider, beginners_enabled=is_beginner)
        Entry.objects.create(
            transaction_id=checkout_session.id,
            event=event,
            rider=rider,
            is_beginner=is_beginner,
            is_20=is_20,
            is_24=is_24,
            class_beginner=rider_event_data["class_beginner"] if is_beginner else "",
            class_20=rider_event_data["class_20"] if is_20 else "",
            class_24=rider_event_data["class_24"] if is_24 else "",
            fee_beginner=rider_event_data["fee_beginner"] if is_beginner else 0,
            fee_20=rider_event_data["fee_20"] if is_20 else 0,
            fee_24=rider_event_data["fee_24"] if is_24 else 0,
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
        # Česká evidence má přednost — přesnější data (čip, tabulka, foto)
        try:
            czech_rider = Rider.objects.get(uci_id=uci_id)
            return JsonResponse(
                {
                    "first_name": czech_rider.first_name,
                    "last_name": czech_rider.last_name,
                    "date_of_birth": czech_rider.date_of_birth,
                    "sex": czech_rider.gender,
                    "plate": czech_rider.plate_display,
                    "transponder_20": czech_rider.transponder_20 or "",
                    "transponder_24": czech_rider.transponder_24 or "",
                    "nationality": czech_rider.nationality or "CZE",
                    "manual_entry": False,
                    "is_czech_rider": True,
                }
            )
        except Rider.DoesNotExist:
            pass

        # Fallback: zahraniční evidence
        try:
            rider = ForeignRider.objects.get(uci_id=uci_id)
            nationality_code = rider.nationality or rider.state or ""
            return JsonResponse(
                {
                    "first_name": rider.first_name,
                    "last_name": rider.last_name,
                    "date_of_birth": rider.date_of_birth,
                    "sex": rider.gender,
                    "plate": rider.plate_display,
                    "transponder_20": rider.transponder_20 or "",
                    "transponder_24": rider.transponder_24 or "",
                    "nationality": nationality_code,
                    "manual_entry": False,
                    "is_czech_rider": False,
                }
            )
        except ForeignRider.DoesNotExist:
            pass

        return JsonResponse(
            {"error": "Rider not found", "manual_entry": True},
            status=200,
        )
    return JsonResponse({"error": "UCI ID is required"}, status=400)


def collect_fees_by_club(event):
    """Přehled startovného na závodě rozdělený po klubech."""
    entries = (
        Entry.objects.filter(
            event=event.pk,
            payment_complete=True,
            checkout=False,
        )
        .select_related("rider", "rider__club")
    )
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
