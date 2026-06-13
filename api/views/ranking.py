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


class RankingCategoryListAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            name="RankingCategories",
            fields={"categories": serializers.ListField(child=serializers.CharField())},
        )
    )
    def get(self, request):
        categories = Categories.get_categories()
        return Response({"categories": categories})


class RankingAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        categories = Categories.get_categories()
        default_category = "Men Under 23"
        category_input = request.query_params.get("category", "").strip()
        category_value = category_input if category_input in categories else default_category

        if re.search("Cruiser", category_value):
            qs = (
                Rider.objects.select_related("club")
                .only(
                    "uci_id", "first_name", "last_name",
                    "club__team_name", "photo",
                    "ranking_24", "points_24", "class_24",
                    "is_active", "is_approved",
                )
                .filter(class_24=category_value[8:], is_active=True, is_approved=True)
                .order_by("-points_24", "last_name", "first_name")
                .exclude(points_24=0)
            )
            cruiser = True
        else:
            qs = (
                Rider.objects.select_related("club")
                .only(
                    "uci_id", "first_name", "last_name",
                    "club__team_name", "photo",
                    "ranking_20", "points_20", "class_20",
                    "is_active", "is_approved",
                )
                .filter(class_20=category_value, is_active=True, is_approved=True)
                .order_by("-points_20", "last_name", "first_name")
                .exclude(points_20=0)
            )
            cruiser = False

        results = [
            {
                "rank": i,
                "uci_id": r.uci_id,
                "first_name": r.first_name,
                "last_name": r.last_name,
                "club": r.club.team_name if r.club else None,
                "photo_url": r.photo_url,
                "points": r.points_24 if cruiser else r.points_20,
                "ranking": r.ranking_24 if cruiser else r.ranking_20,
            }
            for i, r in enumerate(qs, 1)
        ]

        return Response({
            "category": category_value,
            "cruiser": cruiser,
            "count": len(results),
            "results": results,
        })

__all__ = ['RankingCategoryListAPIView', 'RankingAPIView']
