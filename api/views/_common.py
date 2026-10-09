"""Sdílené importy, inline serializery, loggery a pomocné funkce pro api views."""
import logging
import re
import uuid
from io import BytesIO
from datetime import timedelta

import stripe
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.files.base import ContentFile
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.db import transaction as db_tx
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django_filters.rest_framework import DjangoFilterBackend
from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError, features
from rest_framework import generics, status, filters, serializers, throttling as rest_throttling
from bmx.search_filters import NormalizedSearchFilter
from rest_framework.permissions import IsAdminUser, IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema, inline_serializer

from bmx.image_utils import normalize_avatar_image
from rider.models import Rider, ForeignRider
from rider.rider import get_rider_data
from rider.plates import generate_available_plate_values, normalize_plate_value, legacy_plate_int, display_plate
from event.models import CreditTransaction, Event, Entry, Result
from event.models_events import Event as EventModel
from news.models import News
from club.models import Club
from rider.serializers import RiderSerializer, ForeignRiderSerializer
from event.serializers import EventSerializer, EntrySerializer, EventPublicSerializer, EntryDetailSerializer, ResultPublicSerializer
from news.serializer import NewsSerializer
from club.serializers import ClubSerializer, ClubPublicSerializer
from accounts.models import Account, AccountActivationAuditLog, AvatarChangeRequest, FcmDevice, normalize_account_email
from eshop.models import Category, Product, ProductVariant, Order, OrderItem, OrderHistory
from eshop.serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    OrderSerializer,
)
from eshop.cart import Cart
from event.views.payment_helpers import build_credit_checkout_line_item
from ranking.ranking import Categories


_AVATAR_MAX_BYTES = 5 * 1024 * 1024


_AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


ErrorSerializer = inline_serializer(
    name="ApiError",
    fields={"error": serializers.CharField()},
)


DetailSerializer = inline_serializer(
    name="ApiDetail",
    fields={"detail": serializers.CharField()},
)


OkSerializer = inline_serializer(
    name="ApiOk",
    fields={"ok": serializers.BooleanField()},
)


BalanceSerializer = inline_serializer(
    name="ApiBalance",
    fields={
        "ok": serializers.BooleanField(),
        "new_balance": serializers.IntegerField(),
    },
)


UserPayloadSerializer = inline_serializer(
    name="ApiUserPayload",
    fields={
        "id": serializers.IntegerField(),
        "email": serializers.EmailField(),
        "first_name": serializers.CharField(allow_blank=True),
        "last_name": serializers.CharField(allow_blank=True),
        "credit": serializers.IntegerField(),
        "is_staff": serializers.BooleanField(),
        "is_rider": serializers.BooleanField(),
        "is_commissar": serializers.BooleanField(),
        "is_trainer": serializers.BooleanField(),
        "is_club_manager": serializers.BooleanField(),
        "photo_url": serializers.CharField(allow_blank=True, allow_null=True),
        "rider_uci_id": serializers.IntegerField(allow_null=True),
        "mobile_app_subscription": inline_serializer(
            name="ApiMobileAppSub",
            fields={
                "active": serializers.BooleanField(),
                "expires_at": serializers.DateTimeField(allow_null=True),
                "auto_renew": serializers.BooleanField(),
            },
            allow_null=True,
        ),
    },
)


def _validate_avatar_image(uploaded_file):
    if not uploaded_file:
        raise ValueError("Vyber obrázek, který chceš nahrát.")
    if uploaded_file.size > _AVATAR_MAX_BYTES:
        raise ValueError("Avatar může mít maximálně 5 MB.")
    if uploaded_file.content_type not in _AVATAR_ALLOWED_TYPES:
        raise ValueError("Povolené jsou pouze obrázky JPG, PNG nebo WEBP.")
    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.verify()
        uploaded_file.seek(0)
        checked = Image.open(uploaded_file)
        width, height = checked.size
        uploaded_file.seek(0)
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("Nahraný soubor není platný obrázek.")
    if width < 120 or height < 120:
        raise ValueError("Avatar musí mít alespoň 120 × 120 px.")
    if width > 6000 or height > 6000:
        raise ValueError("Avatar je příliš velký.")


def _build_normalized_account_avatar(user, uploaded_file):
    uploaded_file.seek(0)
    try:
        content, extension = normalize_avatar_image(uploaded_file)
    finally:
        uploaded_file.seek(0)

    filename = f"account-avatar-{user.pk}-{uuid.uuid4().hex[:12]}.{extension}"
    return filename, ContentFile(content)


logger = logging.getLogger(__name__)


audit_logger = logging.getLogger("audit")


def _query_bool(value):
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _user_payload(user):
    from rider.mobile_subscriptions import get_active_mobile_app_subscription
    linked_rider = user.riders.filter(is_active=True).order_by("last_name", "first_name").first()
    mobile_sub = get_active_mobile_app_subscription(user)
    return {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "credit": user.credit,
        "is_staff": (user.is_staff or getattr(user, 'is_admin', False) or user.is_superuser),
        "is_rider": user.is_rider,
        "is_commissar": user.is_commissar,
        "is_trainer": user.is_trainer,
        "is_club_manager": user.is_club_manager,
        "photo_url": user.photo_url,
        "rider_uci_id": linked_rider.uci_id if linked_rider else None,
        "mobile_app_subscription": {
            "active": mobile_sub is not None,
            "expires_at": mobile_sub.expires_at.isoformat() if mobile_sub else None,
            "auto_renew": mobile_sub.auto_renew if mobile_sub else False,
        },
    }


def _send_activation_email_api(request, user):
    from django.conf import settings as django_settings
    from django.urls import reverse
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    site = get_current_site(request)
    activation_path = reverse("accounts:activate", kwargs={"uidb64": uid, "token": token})
    context = {
        "user": user,
        "domain": site.domain,
        "site_name": site.name or site.domain,
        "protocol": "https" if request.is_secure() else "http",
        "activation_path": activation_path,
    }
    subject = render_to_string("accounts/account_activation_subject.txt", context).strip()
    body = render_to_string("accounts/account_activation_email.txt", context)
    send_mail(subject, body, None, [user.email])
    AccountActivationAuditLog.objects.create(
        account=user,
        action=AccountActivationAuditLog.Action.SENT,
        source="api_signup",
        email_snapshot=user.email,
    )


def _lookup_foreign_rider(uci_id_raw):
    """Vyhledá jezdce v českém nebo zahraničním registru dle UCI ID."""
    try:
        uci_id = int(str(uci_id_raw).replace(" ", "").replace("-", ""))
    except (ValueError, TypeError):
        return {"found": False, "uci_id": str(uci_id_raw)}

    try:
        rider = Rider.objects.get(uci_id=uci_id, is_active=True, is_approved=True)
        return {
            "found": True,
            "is_czech": True,
            "uci_id": uci_id,
            "first_name": rider.first_name,
            "last_name": rider.last_name,
            "date_of_birth": rider.date_of_birth.isoformat() if rider.date_of_birth else None,
            "gender": rider.gender,
            "nationality": rider.nationality or "CZE",
            "plate": str(rider.plate) if rider.plate else "",
            "transponder_20": rider.transponder_20 or "",
            "transponder_24": rider.transponder_24 or "",
        }
    except Rider.DoesNotExist:
        pass

    try:
        fr = ForeignRider.objects.get(uci_id=uci_id)
        return {
            "found": True,
            "is_czech": False,
            "uci_id": uci_id,
            "first_name": fr.first_name,
            "last_name": fr.last_name,
            "date_of_birth": fr.date_of_birth.isoformat() if fr.date_of_birth else None,
            "gender": fr.gender,
            "nationality": fr.nationality or "",
            "plate": str(fr.plate) if fr.plate else "",
            "transponder_20": fr.transponder_20 or "",
            "transponder_24": fr.transponder_24 or "",
        }
    except ForeignRider.DoesNotExist:
        pass

    return {"found": False, "uci_id": uci_id}


def _calculate_foreign_options(event, dob_str, gender):
    """Vypočítá dostupné kategorie a poplatky pro zahraničního jezdce."""
    from event.views.entry_helpers import enrich_foreign_summary_rows

    base = {
        "uci_id": "0",
        "first_name": "",
        "last_name": "",
        "plate": "",
        "nationality": "",
        "transponder_20": "",
        "transponder_24": "",
        "sex": gender,
        "date_of_birth": dob_str,
    }

    def _enrich(flags):
        row = dict(base, **flags)
        try:
            rows, _ = enrich_foreign_summary_rows(event, [row])
            return rows[0] if rows else {}
        except Exception:
            return {}

    r20 = _enrich({"challenge": True, "championship": False, "cruiser": False})
    r_elite = _enrich({"challenge": False, "championship": True, "cruiser": False})
    r24 = _enrich({"challenge": False, "championship": False, "cruiser": True})

    def _opt(row, class_key, fee_key):
        cls = row.get(class_key, "")
        fee = row.get(fee_key, 0) or 0
        return {"allowed": bool(cls) and fee > 0, "class": cls or None, "fee": fee}

    return {
        "is_20": _opt(r20, "class_20", "fee_20"),
        "is_elite": _opt(r_elite, "class_20", "fee_20"),
        "is_24": _opt(r24, "class_24", "fee_24"),
    }


def _serialize_mobile_subscription(sub):
    if sub is None:
        return None
    return {
        "id": sub.pk,
        "status": sub.status,
        "starts_at": sub.starts_at.isoformat(),
        "expires_at": sub.expires_at.isoformat(),
        "monthly_price": sub.monthly_price,
        "auto_renew": sub.auto_renew,
        "canceled_at": sub.canceled_at.isoformat() if sub.canceled_at else None,
    }


MobileSubscriptionSerializer = inline_serializer(
    name="MobileSubscription",
    fields={
        "id": serializers.IntegerField(),
        "status": serializers.CharField(),
        "starts_at": serializers.DateTimeField(),
        "expires_at": serializers.DateTimeField(),
        "monthly_price": serializers.IntegerField(),
        "auto_renew": serializers.BooleanField(),
        "canceled_at": serializers.DateTimeField(allow_null=True),
    },
)

__all__ = ['_AVATAR_MAX_BYTES', '_AVATAR_ALLOWED_TYPES', 'ErrorSerializer', 'DetailSerializer', 'OkSerializer', 'BalanceSerializer', 'UserPayloadSerializer', '_validate_avatar_image', '_build_normalized_account_avatar', 'logger', 'audit_logger', '_query_bool', '_user_payload', '_send_activation_email_api', '_lookup_foreign_rider', '_calculate_foreign_options', '_serialize_mobile_subscription', 'MobileSubscriptionSerializer']
