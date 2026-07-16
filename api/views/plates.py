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
from rider.rider import extract_licence_identity, get_rider_data
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


class PlateRequestFreePlatesAPIView(APIView):
    """Returns the ordered list of currently available plate numbers."""
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            name="PlateRequestFreePlates",
            fields={"free_plates": serializers.ListField(child=serializers.CharField())},
        )
    )
    def get(self, request):
        used = [
            display_plate(pt, p, fallback="")
            for pt, p in Rider.objects.filter(is_active=True).values_list("plate_text", "plate")
        ]
        return Response({"free_plates": generate_available_plate_values(used)})


class PlateRequestLookupAPIView(APIView):
    """Looks up a UCI ID against the Czech cycling federation and returns rider data."""
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter("uci_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True),
        ],
        responses={
            200: inline_serializer(
                name="PlateRequestLookup",
                fields={
                    "uci_id": serializers.CharField(),
                    "first_name": serializers.CharField(allow_blank=True),
                    "last_name": serializers.CharField(allow_blank=True),
                    "date_of_birth": serializers.DateField(allow_null=True),
                    "gender": serializers.CharField(),
                },
            ),
            400: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def get(self, request):
        uci_id = (request.GET.get("uci_id") or "").strip()
        if not uci_id.isdigit() or len(uci_id) != 11:
            return Response(
                {"error": "UCI ID musí obsahovat přesně 11 číslic."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        existing = Rider.objects.filter(uci_id=uci_id).first()
        if existing:
            return Response(
                {"error": f"Jezdec {existing.first_name} {existing.last_name} již má přidělené startovní číslo."},
                status=status.HTTP_409_CONFLICT,
            )
        data_json, error_msg = get_rider_data(uci_id)
        if error_msg or not data_json:
            not_found = bool(error_msg and "nebyla nalezena" in error_msg)
            return Response(
                {
                    "error": "Licence nebyla nalezena v databázi ČSC."
                    if not_found
                    else "Údaje licence se nepodařilo načíst z ČSC. Zkuste to později."
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                    if not_found
                    else status.HTTP_502_BAD_GATEWAY
                ),
            )
        identity = extract_licence_identity(data_json)
        if identity is None:
            return Response(
                {"error": "ČSC vrátilo neúplné údaje licence. Bez úplné identity nelze pokračovat."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({
            "uci_id": uci_id,
            **identity,
        })


class PlateRequestAPIView(APIView):
    """Creates a new plate-number request (Rider with is_approved=False)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name="PlateRequestCreateRequest",
            fields={
                "uci_id": serializers.CharField(),
                "first_name": serializers.CharField(),
                "last_name": serializers.CharField(),
                "date_of_birth": serializers.DateField(),
                "gender": serializers.CharField(default="Muž"),
                "plate": serializers.CharField(),
                "club_id": serializers.IntegerField(),
                "is_20": serializers.BooleanField(default=False),
                "is_24": serializers.BooleanField(default=False),
                "is_elite": serializers.BooleanField(default=False),
                "emergency_contact": serializers.CharField(),
                "emergency_phone": serializers.CharField(),
            },
        ),
        responses={201: RiderSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
    )
    def post(self, request):
        data = request.data

        uci_id = str(data.get("uci_id", "")).strip()
        first_name = str(data.get("first_name", "")).strip()
        last_name = str(data.get("last_name", "")).strip()
        date_of_birth_str = str(data.get("date_of_birth", "")).strip()
        gender = str(data.get("gender", "Muž")).strip()
        plate = str(data.get("plate", "")).strip()
        club_id = data.get("club_id")
        is_20 = bool(data.get("is_20", False))
        is_24 = bool(data.get("is_24", False))
        is_elite = bool(data.get("is_elite", False))
        emergency_contact = str(data.get("emergency_contact", "")).strip()
        emergency_phone = str(data.get("emergency_phone", "")).strip()

        # --- Validation ---
        missing = []
        if not uci_id:           missing.append("UCI ID")
        if not first_name:       missing.append("jméno")
        if not last_name:        missing.append("příjmení")
        if not date_of_birth_str: missing.append("datum narození")
        if not plate:            missing.append("startovní číslo")
        if not club_id:          missing.append("klub")
        if not emergency_contact: missing.append("nouzový kontakt")
        if not emergency_phone:  missing.append("telefon nouzového kontaktu")
        if missing:
            return Response(
                {"error": f"Povinná pole chybí: {', '.join(missing)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not uci_id.isdigit() or len(uci_id) != 11:
            return Response({"error": "UCI ID musí obsahovat přesně 11 číslic."}, status=status.HTTP_400_BAD_REQUEST)

        if not (is_20 or is_24):
            return Response({"error": "Vyber alespoň jednu kategorii (20\" nebo 24\")."}, status=status.HTTP_400_BAD_REQUEST)

        if Rider.objects.filter(uci_id=uci_id).exists():
            return Response({"error": "Jezdec s tímto UCI ID již existuje."}, status=status.HTTP_409_CONFLICT)

        import datetime
        try:
            dob = datetime.datetime.strptime(date_of_birth_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Datum narození musí být ve formátu YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        club = Club.objects.filter(pk=club_id, is_active=True).first()
        if not club:
            return Response({"error": "Vybraný klub nebyl nalezen."}, status=status.HTTP_400_BAD_REQUEST)

        # Verify plate is still free
        used = {
            display_plate(pt, p, fallback="")
            for pt, p in Rider.objects.filter(is_active=True).values_list("plate_text", "plate")
        }
        normalized_plate = normalize_plate_value(plate)
        if normalized_plate in used:
            return Response({"error": "Vybrané startovní číslo je již obsazeno."}, status=status.HTTP_409_CONFLICT)

        Rider.objects.create(
            first_name=first_name,
            last_name=last_name,
            date_of_birth=dob,
            gender=gender,
            uci_id=uci_id,
            is_20=is_20,
            is_24=is_24,
            is_elite=is_elite,
            plate_text=normalized_plate,
            plate=legacy_plate_int(normalized_plate),
            club=club,
            is_active=True,
            is_approved=False,
            emergency_contact=emergency_contact,
            emergency_phone=emergency_phone,
        )
        return Response(
            {"message": "Žádost o přidělení startovního čísla byla odeslána. Po schválení administrátorem bude číslo přiděleno."},
            status=status.HTTP_201_CREATED,
        )

__all__ = ['PlateRequestFreePlatesAPIView', 'PlateRequestLookupAPIView', 'PlateRequestAPIView']
