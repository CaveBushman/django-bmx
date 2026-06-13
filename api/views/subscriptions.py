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


class MobileAppSubscriptionAPIView(APIView):
    """Správa předplatného mobilní aplikace pro přihlášeného uživatele."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: inline_serializer(
            name="MobileSubStatus",
            fields={
                "subscription": MobileSubscriptionSerializer,
                "price": serializers.IntegerField(),
                "balance": serializers.IntegerField(),
            },
        )}
    )
    def get(self, request):
        from rider.mobile_subscriptions import get_active_mobile_app_subscription, get_current_season_settings
        sub = get_active_mobile_app_subscription(request.user)
        season = get_current_season_settings()
        price = season.mobile_app_annual_price if season else 0
        return Response({
            "subscription": _serialize_mobile_subscription(sub),
            "price": price,
            "balance": request.user.credit,
        })

    @extend_schema(
        request=inline_serializer(
            name="MobileSubPurchaseRequest",
            fields={"promo_code": serializers.CharField(required=False, allow_blank=True)},
        ),
        responses={201: inline_serializer(
            name="MobileSubPurchaseResponse",
            fields={
                "subscription": MobileSubscriptionSerializer,
                "new_balance": serializers.IntegerField(),
                "created": serializers.BooleanField(),
            },
        ), 400: ErrorSerializer},
    )
    def post(self, request):
        from rider.mobile_subscriptions import purchase_mobile_app_subscription
        promo_code = request.data.get("promo_code", "") or None
        try:
            sub, created = purchase_mobile_app_subscription(request.user, promo_code_str=promo_code)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        request.user.refresh_from_db(fields=["credit"])
        return Response(
            {"subscription": _serialize_mobile_subscription(sub), "new_balance": request.user.credit, "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(responses={200: BalanceSerializer, 400: ErrorSerializer})
    def delete(self, request):
        from rider.mobile_subscriptions import cancel_mobile_app_subscription, get_active_mobile_app_subscription
        sub = get_active_mobile_app_subscription(request.user)
        if sub is None:
            return Response({"error": "Nemáte aktivní předplatné mobilní aplikace."}, status=status.HTTP_400_BAD_REQUEST)
        cancel_mobile_app_subscription(sub)
        return Response({"ok": True, "new_balance": request.user.credit})


class MobileAppSubscriptionResumeAPIView(APIView):
    """Obnovení automatického prodloužení předplatného mobilní aplikace."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: BalanceSerializer, 400: ErrorSerializer})
    def post(self, request):
        from rider.models import MobileAppSubscription
        from rider.mobile_subscriptions import resume_mobile_app_subscription
        sub = (
            MobileAppSubscription.objects.filter(
                user=request.user,
                status__in=[MobileAppSubscription.STATUS_ACTIVE, MobileAppSubscription.STATUS_PAST_DUE],
            )
            .order_by("-expires_at")
            .first()
        )
        if sub is None:
            return Response({"error": "Žádné předplatné k obnovení."}, status=status.HTTP_400_BAD_REQUEST)
        resume_mobile_app_subscription(sub)
        return Response({"ok": True, "new_balance": request.user.credit})


class PromoCodeValidateAPIView(APIView):
    """Ověření platnosti promo kódu před použitím."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name="PromoCodeValidateRequest",
            fields={
                "code": serializers.CharField(),
                "product": serializers.CharField(required=False, default="mobile_app"),
            },
        ),
        responses={200: inline_serializer(
            name="PromoCodeValidateResponse",
            fields={
                "valid": serializers.BooleanField(),
                "discount_type": serializers.CharField(),
                "discount_value": serializers.IntegerField(),
                "product": serializers.CharField(),
                "error": serializers.CharField(required=False),
            },
        )},
    )
    def post(self, request):
        from rider.models import PromoCode, PromoCodeUsage
        code_str = (request.data.get("code") or "").strip().upper()
        product = request.data.get("product", PromoCode.PRODUCT_MOBILE_APP)

        try:
            promo = PromoCode.objects.get(code=code_str)
        except PromoCode.DoesNotExist:
            return Response({"valid": False, "error": "Promo kód neexistuje."})

        if not promo.is_valid():
            return Response({"valid": False, "error": "Promo kód není platný nebo byl vyčerpán."})

        if promo.product not in (product, PromoCode.PRODUCT_ALL):
            return Response({"valid": False, "error": "Promo kód nelze použít pro tento produkt."})

        if PromoCodeUsage.objects.filter(promo_code=promo, user=request.user).exists():
            return Response({"valid": False, "error": "Tento promo kód jste již použili."})

        return Response({
            "valid": True,
            "discount_type": promo.discount_type,
            "discount_value": promo.discount_value,
            "product": promo.product,
        })


class PromoCodeGenerateAPIView(APIView):
    """Generování nového promo kódu (pouze admin)."""
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=inline_serializer(
            name="PromoCodeGenerateRequest",
            fields={
                "product": serializers.ChoiceField(choices=["mobile_app", "rider_stats", "trainer_club", "trainer_extended", "all"], required=False),
                "discount_type": serializers.ChoiceField(choices=["percent", "fixed", "free"], required=False),
                "discount_value": serializers.IntegerField(required=False, default=100),
                "max_uses": serializers.IntegerField(required=False, allow_null=True),
                "valid_until": serializers.DateTimeField(required=False, allow_null=True),
                "description": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={201: inline_serializer(
            name="PromoCodeGenerateResponse",
            fields={
                "code": serializers.CharField(),
                "product": serializers.CharField(),
                "discount_type": serializers.CharField(),
                "discount_value": serializers.IntegerField(),
                "max_uses": serializers.IntegerField(allow_null=True),
                "valid_until": serializers.DateTimeField(allow_null=True),
            },
        ), 400: ErrorSerializer},
    )
    def post(self, request):
        from rider.models import PromoCode
        product = request.data.get("product", PromoCode.PRODUCT_MOBILE_APP)
        discount_type = request.data.get("discount_type", PromoCode.DISCOUNT_FREE)
        discount_value = request.data.get("discount_value", 100)
        max_uses = request.data.get("max_uses", None)
        valid_until = request.data.get("valid_until", None)
        description = request.data.get("description", "")

        valid_products = [c[0] for c in PromoCode.PRODUCT_CHOICES]
        valid_discount_types = [c[0] for c in PromoCode.DISCOUNT_CHOICES]
        if product not in valid_products:
            return Response({"error": "Neplatný produkt."}, status=status.HTTP_400_BAD_REQUEST)
        if discount_type not in valid_discount_types:
            return Response({"error": "Neplatný typ slevy."}, status=status.HTTP_400_BAD_REQUEST)

        promo = PromoCode.objects.create(
            product=product,
            discount_type=discount_type,
            discount_value=int(discount_value),
            max_uses=int(max_uses) if max_uses is not None else None,
            valid_until=valid_until,
            description=description,
            created_by=request.user,
        )
        return Response({
            "code": promo.code,
            "product": promo.product,
            "discount_type": promo.discount_type,
            "discount_value": promo.discount_value,
            "max_uses": promo.max_uses,
            "valid_until": promo.valid_until.isoformat() if promo.valid_until else None,
        }, status=status.HTTP_201_CREATED)

__all__ = ['MobileAppSubscriptionAPIView', 'MobileAppSubscriptionResumeAPIView', 'PromoCodeValidateAPIView', 'PromoCodeGenerateAPIView']
