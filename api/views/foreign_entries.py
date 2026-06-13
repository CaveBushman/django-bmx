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


from api.views._common import *  # noqa: F401,F403
from api.views._common import (  # explicitní helpery (import * je nepřenáší jako podtržítkové)
    _AVATAR_MAX_BYTES, _AVATAR_ALLOWED_TYPES,
    _validate_avatar_image, _build_normalized_account_avatar,
    _query_bool, _user_payload, _send_activation_email_api,
    _lookup_foreign_rider, _calculate_foreign_options,
    _serialize_mobile_subscription,
    logger, audit_logger,
)


class ForeignEventEntryInfoAPIView(APIView):
    """Vrátí info pro přihlášení zahraničního jezdce — lookup jezdce + dostupné kategorie."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("uci_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("dob", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("gender", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request, pk):
        from event.func import is_registration_open

        event = get_object_or_404(
            Event.objects.select_related("classes_and_fees_like"), pk=pk
        )

        result = {
            "event_id": event.pk,
            "event_name": event.name,
            "registration_open": is_registration_open(event),
            "rider": None,
            "options": None,
        }

        uci_id_raw = request.query_params.get("uci_id")
        dob_param = request.query_params.get("dob")
        gender_param = request.query_params.get("gender")

        rider_data = None
        if uci_id_raw:
            rider_data = _lookup_foreign_rider(uci_id_raw)
            result["rider"] = rider_data

        dob = (rider_data.get("date_of_birth") if rider_data else None) or dob_param
        gender = (rider_data.get("gender") if rider_data else None) or gender_param

        if dob and gender:
            result["options"] = _calculate_foreign_options(event, dob, gender)

        return Response(result)


class ForeignEventEnterAPIView(APIView):
    """Přihlásí zahraničního jezdce na závod — strhne kredit přihlášenému uživateli."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name="ForeignEventEnterRequest",
            fields={
                "uci_id": serializers.CharField(),
                "first_name": serializers.CharField(),
                "last_name": serializers.CharField(),
                "date_of_birth": serializers.DateField(),
                "gender": serializers.CharField(default="Muž"),
                "nationality": serializers.CharField(required=False, allow_blank=True),
                "plate": serializers.CharField(required=False, allow_blank=True),
                "transponder_20": serializers.CharField(required=False, allow_blank=True),
                "transponder_24": serializers.CharField(required=False, allow_blank=True),
                "is_20": serializers.BooleanField(default=False),
                "is_24": serializers.BooleanField(default=False),
                "is_elite": serializers.BooleanField(default=False),
            },
        ),
        responses={
            201: inline_serializer(
                name="ForeignEventEnterResponse",
                fields={
                    "id": serializers.IntegerField(),
                    "event_name": serializers.CharField(),
                    "rider_first_name": serializers.CharField(),
                    "rider_last_name": serializers.CharField(),
                    "uci_id": serializers.CharField(),
                    "class_20": serializers.CharField(allow_blank=True),
                    "class_24": serializers.CharField(allow_blank=True),
                    "total_fee": serializers.IntegerField(),
                    "new_balance": serializers.IntegerField(),
                },
            ),
            400: ErrorSerializer,
            402: inline_serializer(
                name="ForeignInsufficientCreditError",
                fields={
                    "error": serializers.CharField(),
                    "required": serializers.IntegerField(),
                    "balance": serializers.IntegerField(),
                },
            ),
            409: ErrorSerializer,
        },
    )
    def post(self, request, pk):
        from event.func import is_registration_open
        from event.models_entries import EntryForeign
        from event.credit import calculate_user_balance
        from event.models import DebetTransaction

        event = get_object_or_404(
            Event.objects.select_related("classes_and_fees_like"), pk=pk
        )

        if not is_registration_open(event):
            return Response(
                {"error": "Registrace na tento závod není otevřena."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uci_id = str(request.data.get("uci_id", "")).strip()
        first_name = str(request.data.get("first_name", "")).strip()
        last_name = str(request.data.get("last_name", "")).strip()
        date_of_birth = request.data.get("date_of_birth")
        gender = str(request.data.get("gender", "Muž")).strip()
        nationality = str(request.data.get("nationality", "")).strip()
        plate = str(request.data.get("plate", "")).strip()
        transponder_20 = str(request.data.get("transponder_20", "")).strip()
        transponder_24 = str(request.data.get("transponder_24", "")).strip()
        is_20 = bool(request.data.get("is_20", False))
        is_24 = bool(request.data.get("is_24", False))
        is_elite = bool(request.data.get("is_elite", False))

        if not uci_id:
            return Response({"error": "UCI ID je povinné."}, status=status.HTTP_400_BAD_REQUEST)
        if not first_name or not last_name:
            return Response({"error": "Jméno a příjmení jsou povinné."}, status=status.HTTP_400_BAD_REQUEST)
        if not date_of_birth:
            return Response({"error": "Datum narození je povinné."}, status=status.HTTP_400_BAD_REQUEST)
        if not (is_20 or is_24):
            return Response({"error": "Vyber alespoň jednu kategorii (is_20 nebo is_24)."}, status=status.HTTP_400_BAD_REQUEST)

        from event.views.entry_helpers import enrich_foreign_summary_rows

        row = {
            "sex": gender,
            "date_of_birth": date_of_birth,
            "challenge": is_20 and not is_elite,
            "championship": is_20 and is_elite,
            "cruiser": is_24,
            "uci_id": uci_id,
            "first_name": first_name,
            "last_name": last_name,
            "plate": plate,
            "nationality": nationality,
            "transponder_20": transponder_20,
            "transponder_24": transponder_24,
        }

        try:
            enriched_rows, total_fee = enrich_foreign_summary_rows(event, [row])
        except Exception as exc:
            return Response({"error": f"Chyba výpočtu poplatku: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        if not enriched_rows:
            return Response({"error": "Nepodařilo se vypočítat poplatek."}, status=status.HTTP_400_BAD_REQUEST)

        r = enriched_rows[0]
        class_20 = r.get("class_20") or ""
        class_24 = r.get("class_24") or ""
        fee_20 = r.get("fee_20") or 0
        fee_24 = r.get("fee_24") or 0

        user = request.user
        if total_fee > 0 and user.credit < total_fee:
            return Response(
                {
                    "error": f"Nedostatek kreditu. Potřeba: {total_fee} Kč, zůstatek: {user.credit} Kč.",
                    "required": total_fee,
                    "balance": user.credit,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        with db_tx.atomic():
            already = EntryForeign.objects.filter(
                event=event,
                uci_id=uci_id,
                payment_complete=True,
                checkout=False,
                is_20=is_20,
                is_elite=is_elite,
                is_24=is_24,
            ).exists()
            if already:
                return Response(
                    {"error": "Jezdec je na tento závod a kategorii již přihlášen."},
                    status=status.HTTP_409_CONFLICT,
                )

            entry = EntryForeign.objects.create(
                event=event,
                user=user,
                uci_id=uci_id,
                first_name=first_name,
                last_name=last_name,
                date_of_birth=date_of_birth or None,
                gender=gender,
                nationality=nationality,
                plate=plate,
                transponder_20=transponder_20,
                transponder_24=transponder_24,
                club="",
                transponder="",
                is_20=is_20,
                is_24=is_24,
                is_elite=is_elite,
                class_20=class_20,
                class_24=class_24,
                fee_20=fee_20,
                fee_24=fee_24,
                payment_complete=True,
                customer_name=f"{user.first_name} {user.last_name}".strip(),
                customer_email=user.email,
            )

            if total_fee > 0:
                DebetTransaction.objects.create(
                    user=user,
                    foreign_entry=entry,
                    amount=total_fee,
                )
                user.credit = calculate_user_balance(user.id)
                user.save(update_fields=["credit"])

        from event.views.entry_helpers import sync_entry_to_foreign_rider_registry
        try:
            sync_entry_to_foreign_rider_registry(entry)
        except Exception:
            pass  # Non-critical — entry was created, registry sync is best-effort

        return Response(
            {
                "id": entry.pk,
                "event_name": event.name,
                "rider_first_name": entry.first_name,
                "rider_last_name": entry.last_name,
                "uci_id": entry.uci_id,
                "class_20": entry.class_20,
                "class_24": entry.class_24,
                "total_fee": total_fee,
                "new_balance": user.credit,
            },
            status=status.HTTP_201_CREATED,
        )


class ForeignEntryCancelAPIView(APIView):
    """Storno přihlášky zahraničního jezdce — refundace kreditu."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: BalanceSerializer, 400: ErrorSerializer})
    def post(self, request, pk):
        from event.models_entries import EntryForeign
        from event.models import DebetTransaction
        from event.credit import calculate_user_balance
        from event.func import is_unregistration_open

        entry = get_object_or_404(
            EntryForeign,
            pk=pk,
            user=request.user,
            payment_complete=True,
            checkout=False,
        )

        if not is_unregistration_open(entry.event):
            return Response(
                {"error": "Lhůta pro odhlášení již vypršela."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        with db_tx.atomic():
            DebetTransaction.objects.filter(user=user, foreign_entry=entry).delete()
            entry.delete()
            user.credit = calculate_user_balance(user.id)
            user.save(update_fields=["credit"])

        return Response({"ok": True, "new_balance": user.credit}, status=status.HTTP_200_OK)

__all__ = ['ForeignEventEntryInfoAPIView', 'ForeignEventEnterAPIView', 'ForeignEntryCancelAPIView']
