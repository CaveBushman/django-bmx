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


class GlobalSearchAPIView(APIView):
    """
    Fulltextové hledání přes jezdce, závody a novinky.

    GET /api/v1/search/?q=novak&types=riders,events,news&limit=5
    """
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, description="Hledaný výraz (min. 2 znaky)"),
            OpenApiParameter("types", OpenApiTypes.STR, description="Typy výsledků: riders,events,news (výchozí: vše)"),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Max. výsledků na typ (výchozí: 5, max: 20)"),
        ],
        responses={200: inline_serializer(
            name="SearchResults",
            fields={
                "query": serializers.CharField(),
                "riders": serializers.ListField(child=serializers.DictField()),
                "events": serializers.ListField(child=serializers.DictField()),
                "news": serializers.ListField(child=serializers.DictField()),
            },
        )},
    )
    def get(self, request):
        from django.db.models import Q as DQ
        from bmx.text_normalization import normalize_search_text

        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response({"query": q, "riders": [], "events": [], "news": []})

        types_param = request.query_params.get("types", "riders,events,news")
        active_types = {t.strip() for t in types_param.split(",")}
        try:
            limit = min(int(request.query_params.get("limit", 5)), 20)
        except (ValueError, TypeError):
            limit = 5

        results = {"query": q, "riders": [], "events": [], "news": []}
        q_upper = q.upper()
        q_normalized = normalize_search_text(q)

        if "riders" in active_types:
            rider_qs = (
                Rider.objects.filter(is_active=True, is_approved=True)
                .filter(
                    DQ(search_text_normalized__icontains=q_normalized)
                    | DQ(first_name__icontains=q)
                    | DQ(last_name__icontains=q)
                )
                .select_related("club")[:limit]
            )
            results["riders"] = [
                {
                    "uci_id": r.uci_id,
                    "first_name": r.first_name,
                    "last_name": r.last_name,
                    "club": str(r.club or ""),
                    "class_20": r.class_20 or "",
                    "plate": r.plate_display,
                }
                for r in rider_qs
            ]

        if "events" in active_types:
            event_qs = (
                Event.objects.filter(
                    DQ(name__icontains=q) | DQ(organizer__team_name__icontains=q)
                )
                .select_related("organizer")
                .order_by("-date")[:limit]
            )
            results["events"] = [
                {
                    "id": e.id,
                    "name": e.name,
                    "date": e.date.isoformat() if e.date else "",
                    "organizer": str(e.organizer or ""),
                    "type": e.type_for_ranking,
                    "canceled": e.canceled,
                }
                for e in event_qs
            ]

        if "news" in active_types:
            from news.models import News
            news_qs = (
                News.objects.filter(published=True)
                .filter(DQ(title__icontains=q) | DQ(perex__icontains=q))
                .order_by("-created_date")[:limit]
            )
            results["news"] = [
                {
                    "id": n.id,
                    "title": n.title,
                    "perex": (n.perex or "")[:160],
                    "created": n.created_date.isoformat(),
                    "slug": n.slug,
                }
                for n in news_qs
            ]

        return Response(results)

__all__ = ['GlobalSearchAPIView']
