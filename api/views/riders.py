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


class RiderList(generics.ListAPIView):
    queryset = Rider.objects.filter(is_active=True).select_related("club").only(
        'id', 'uci_id', 'first_name', 'middle_name', 'last_name',
        'nationality', 'gender', 'photo', 'club_id',
        'is_20', 'is_24', 'is_elite', 'is_active', 'is_approved',
        'class_20', 'class_24', 'plate_text',
        'transponder_20', 'transponder_24',
        'points_20', 'points_24', 'ranking_20', 'ranking_24',
        'club__team_name', 'search_text_normalized',
    )
    serializer_class = RiderSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, NormalizedSearchFilter, filters.OrderingFilter]
    filterset_fields = ["club", "class_20", "class_24", "is_20", "is_24", "is_elite", "gender"]
    search_fields = ["search_text_normalized", "=uci_id", "plate_text"]
    ordering_fields = ["last_name", "first_name", "uci_id"]
    ordering = ["last_name", "first_name"]


class RiderDetail(generics.RetrieveAPIView):
    queryset = Rider.objects.filter(is_active=True).select_related("club").only(
        'id', 'uci_id', 'first_name', 'middle_name', 'last_name',
        'nationality', 'gender', 'photo', 'club_id',
        'is_20', 'is_24', 'is_elite', 'is_active', 'is_approved',
        'class_20', 'class_24', 'plate_text',
        'transponder_20', 'transponder_24',
        'points_20', 'points_24', 'ranking_20', 'ranking_24',
        'club__team_name',
    )
    serializer_class = RiderSerializer
    lookup_field = "uci_id"
    permission_classes = [AllowAny]


class RiderResultsAPIView(APIView):
    """Výsledky jezdce za posledních 12 kalendářních měsíců."""
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            name="RiderResult",
            many=True,
            fields={
                "event_id": serializers.IntegerField(allow_null=True),
                "event_name": serializers.CharField(allow_blank=True),
                "date": serializers.DateField(allow_null=True),
                "category": serializers.CharField(allow_blank=True),
                "place": serializers.IntegerField(allow_null=True),
                "points": serializers.IntegerField(allow_null=True),
                "is_20": serializers.BooleanField(),
                "marked_20": serializers.BooleanField(),
                "marked_24": serializers.BooleanField(),
            },
        )
    )
    def get(self, request, uci_id):
        from datetime import date
        today = date.today()
        try:
            cutoff = today.replace(year=today.year - 1)
        except ValueError:
            # 29. února v přestupném roce → fallback na 28. února
            cutoff = date(today.year - 1, today.month, 28)

        results = (
            Result.objects
            .filter(rider_id=uci_id, date__gte=cutoff, is_beginner=False)
            .select_related("event")
            .order_by("-date", "-id")
        )
        data = [
            {
                "event_id": r.event_id,
                "event_name": r.event.name if r.event else (r.organizer or ""),
                "date": r.date.isoformat() if r.date else None,
                "category": r.category or "",
                "place": r.place,
                "points": r.points,
                "is_20": r.is_20,
                "marked_20": bool(r.marked_20),
                "marked_24": bool(r.marked_24),
            }
            for r in results
        ]
        return Response(data)


class RiderNewAPIView(generics.CreateAPIView):
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer
    permission_classes = [IsAdminUser]


class RiderLicenseAPIView(APIView):
    """
    License check for commissars.
    Identity: local DB (primary) → ČSC licenseinfo (fallback for unknown riders).
    Validity: ČSC validuciid endpoint (null when unreachable).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, uci_id):
        is_commissar = getattr(request.user, 'is_commissar', False)
        is_admin = (
            getattr(request.user, 'is_admin', False)
            or request.user.is_superuser
            or request.user.is_staff
        )
        if not (is_commissar or is_admin):
            return Response({"error": "Permission denied."}, status=403)

        from rider.rider import get_api_token, get_rider_data
        import requests as req_lib
        from datetime import date

        # ── 1. Identity: local DB first ──────────────────────────────────────
        local = Rider.objects.filter(uci_id=uci_id).first()

        if local:
            first_name = local.first_name
            last_name  = local.last_name
            dob        = str(local.date_of_birth) if local.date_of_birth else ""
            gender     = local.gender or ""
        else:
            # Fallback: ask ČSC API (handles riders not yet in our DB)
            data_json, error = get_rider_data(uci_id)
            if not data_json:
                return Response(
                    {"error": error or "Jezdec nebyl nalezen."},
                    status=404,
                )
            first_name = (data_json.get("firstName") or "").strip()
            last_name  = (data_json.get("lastName") or "").strip()
            dob        = (data_json.get("birth") or "")[:10]
            gender     = (data_json.get("sex") or {}).get("code", "")

        # ── 2. Validity: ČSC validuciid ──────────────────────────────────────
        is_valid = None
        token = get_api_token()
        if token:
            try:
                resp = req_lib.get(
                    "https://portal.api.czechcyclingfederation.com/api/services/validuciid",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"year": date.today().year, "uciId": uci_id},
                    timeout=10,
                    verify=True,
                )
                if resp.ok:
                    is_valid = resp.json().get("valid", False)
            except Exception:
                pass

        return Response({
            "uci_id":         uci_id,
            "first_name":     first_name,
            "last_name":      last_name,
            "date_of_birth":  dob,
            "gender":         gender,
            "license_valid":  is_valid,
        })


class RiderAdminAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer
    lookup_field = "uci_id"
    permission_classes = [IsAdminUser]


class ForeignRiderList(generics.ListAPIView):
    queryset = ForeignRider.objects.all()
    serializer_class = ForeignRiderSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["nationality", "class_20", "class_24", "is_20", "is_24", "gender"]
    search_fields = ["first_name", "last_name", "uci_id"]
    ordering_fields = ["last_name", "first_name", "uci_id"]
    ordering = ["last_name", "first_name"]


class ForeignRiderDetail(generics.RetrieveAPIView):
    queryset = ForeignRider.objects.all()
    serializer_class = ForeignRiderSerializer
    lookup_field = "uci_id"
    permission_classes = [IsAdminUser]

__all__ = ['RiderList', 'RiderDetail', 'RiderResultsAPIView', 'RiderNewAPIView', 'RiderLicenseAPIView', 'RiderAdminAPIView', 'ForeignRiderList', 'ForeignRiderDetail']
