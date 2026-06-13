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


class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [rest_throttling.ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=inline_serializer(
            name="LoginRequest",
            fields={
                "email": serializers.EmailField(),
                "password": serializers.CharField(write_only=True),
            },
        ),
        responses={
            200: inline_serializer(
                name="LoginResponse",
                fields={
                    "access": serializers.CharField(),
                    "refresh": serializers.CharField(),
                    "expires_at": serializers.DateTimeField(),
                    "user": UserPayloadSerializer,
                },
            ),
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
        },
    )
    def post(self, request):
        email = normalize_account_email(request.data.get("email", ""))
        password = request.data.get("password", "")

        if not email or not password:
            return Response(
                {"error": "Zadej e-mail a heslo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Authenticate manually so we can distinguish "wrong password" vs "inactive account"
        # (Django's authenticate() returns None for both, hiding the distinction)
        User = get_user_model()
        try:
            user_obj = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Nesprávný e-mail nebo heslo."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user_obj.check_password(password):
            return Response(
                {"error": "Nesprávný e-mail nebo heslo."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user_obj.is_active:
            return Response(
                {"error": "Účet není aktivní."},
                status=status.HTTP_403_FORBIDDEN,
            )

        user = user_obj

        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "expires_at": timezone.now() + refresh.access_token.lifetime,
            "user": _user_payload(user),
        })


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name="LogoutRequest",
            fields={"refresh": serializers.CharField(required=False, allow_blank=True)},
        ),
        responses={204: OpenApiResponse(description="Odhlášeno.")},
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class FcmTokenAPIView(APIView):
    """Register or update the FCM push token for the calling user's device."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name="FcmTokenRequest",
            fields={"fcm_token": serializers.CharField()},
        ),
        responses={204: OpenApiResponse(description="Token uložen.")},
    )
    def post(self, request):
        token = (request.data.get("fcm_token") or "").strip()
        if not token:
            return Response({"detail": "fcm_token required."}, status=status.HTTP_400_BAD_REQUEST)
        FcmDevice.objects.update_or_create(
            token=token,
            defaults={"user": request.user},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=inline_serializer(
            name="FcmTokenDeleteRequest",
            fields={"fcm_token": serializers.CharField(required=False, allow_blank=True)},
        ),
        responses={204: OpenApiResponse(description="Token odstraněn.")},
    )
    def delete(self, request):
        token = (request.data.get("fcm_token") or "").strip()
        if token:
            FcmDevice.objects.filter(user=request.user, token=token).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserPayloadSerializer)
    def get(self, request):
        return Response(_user_payload(request.user))

    @extend_schema(
        request=inline_serializer(
            name="MeUpdateRequest",
            fields={
                "first_name": serializers.CharField(required=False, allow_blank=True),
                "last_name": serializers.CharField(required=False, allow_blank=True),
                "photo": serializers.ImageField(required=False),
            },
        ),
        responses={200: UserPayloadSerializer, 400: ErrorSerializer},
    )
    def patch(self, request):
        user = request.user
        allowed = {"first_name", "last_name"}
        data = {k: v for k, v in request.data.items() if k in allowed}
        for field, value in data.items():
            setattr(user, field, value)

        update_fields = list(data.keys())
        uploaded_photo = request.FILES.get("photo")
        if uploaded_photo:
            try:
                _validate_avatar_image(uploaded_photo)
                filename, normalized_image = _build_normalized_account_avatar(user, uploaded_photo)
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            user.photo.save(filename, normalized_image, save=False)
            update_fields.append("photo")

        if update_fields:
            user.save(update_fields=update_fields)
        return Response(_user_payload(user))


class CreditTopUpAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name="CreditTopUpRequest",
            fields={"amount": serializers.IntegerField(min_value=100, max_value=10000)},
        ),
        responses={
            201: inline_serializer(
                name="CreditTopUpResponse",
                fields={
                    "checkout_url": serializers.URLField(),
                    "session_id": serializers.CharField(),
                },
            ),
            400: DetailSerializer,
            502: DetailSerializer,
        },
    )
    def post(self, request):
        try:
            amount = int(request.data.get("amount", 0))
        except (TypeError, ValueError):
            return Response(
                {"detail": "Neplatná částka."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if amount < 100:
            return Response(
                {"detail": "Minimální částka pro nákup kreditu je 100 Kč."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount > 10000:
            return Response(
                {"detail": "Maximální částka pro nákup kreditu je 10 000 Kč."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=build_credit_checkout_line_item(request.user, amount),
                mode="payment",
                customer_email=request.user.email,
                success_url=(
                    settings.YOUR_DOMAIN
                    + "/event/success-credit?session_id={CHECKOUT_SESSION_ID}"
                ),
                cancel_url=settings.YOUR_DOMAIN + "/event/cancel?source=credit",
            )
            CreditTransaction.objects.create(
                transaction_id=checkout_session.id,
                amount=amount,
                user=request.user,
                kind=CreditTransaction.Kind.TOPUP,
            )
            audit_logger.info(
                "api_credit_checkout_started user_id=%s amount=%s session_id=%s",
                request.user.id,
                amount,
                checkout_session.id,
            )
            return Response(
                {
                    "checkout_url": checkout_session.url,
                    "session_id": checkout_session.id,
                },
                status=status.HTTP_201_CREATED,
            )
        except stripe.error.StripeError as error:
            audit_logger.exception(
                "api_credit_checkout_failed user_id=%s amount=%s",
                request.user.id,
                amount,
            )
            return Response(
                {"detail": str(error)},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class PasswordChangeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name="PasswordChangeRequest",
            fields={
                "old_password": serializers.CharField(write_only=True),
                "new_password": serializers.CharField(write_only=True, min_length=8),
            },
        ),
        responses={204: OpenApiResponse(description="Heslo změněno."), 400: ErrorSerializer},
    )
    def post(self, request):
        old_password = request.data.get("old_password", "")
        new_password = request.data.get("new_password", "")

        if not old_password or not new_password:
            return Response(
                {"error": "Vyplň stávající i nové heslo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(old_password):
            return Response(
                {"error": "Stávající heslo není správné."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {"error": "Nové heslo musí mít alespoň 8 znaků."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AvatarRequestAPIView(APIView):
    """
    GET  — stav žádosti o avatar pro přihlášeného uživatele (účet + navázaní jezdci)
    POST — odešle žádost o nový avatar ke schválení administrátorem

    POST přijímá multipart/form-data:
      image          — soubor (JPG / PNG / WEBP, max 5 MB, min 120 × 120 px)
      target_type    — "account" (výchozí) nebo "rider"
      target_rider_id — PK jezdce (povinné pokud target_type == "rider")
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        AvatarChangeRequest.expire_stale_requests()
        account_req = AvatarChangeRequest.objects.filter(
            target_account=request.user,
            status=AvatarChangeRequest.STATUS_PENDING,
        ).first()
        linked_riders = list(
            request.user.riders.filter(is_active=True).only("id", "first_name", "last_name")
        )
        rider_pending = {
            req.target_rider_id: req.created.isoformat()
            for req in AvatarChangeRequest.objects.filter(
                target_rider__in=linked_riders,
                status=AvatarChangeRequest.STATUS_PENDING,
            ).only("target_rider_id", "created")
        }
        return Response({
            "account": {
                "pending": account_req is not None,
                "submitted_at": account_req.created.isoformat() if account_req else None,
            },
            "linked_riders": [
                {
                    "id": rider.id,
                    "name": f"{rider.first_name} {rider.last_name}",
                    "pending": rider.id in rider_pending,
                    "submitted_at": rider_pending.get(rider.id),
                }
                for rider in linked_riders
            ],
        })

    @extend_schema(
        request=inline_serializer(
            name="AvatarRequestCreateRequest",
            fields={
                "image": serializers.ImageField(),
                "target_type": serializers.ChoiceField(choices=["account", "rider"], default="account"),
                "target_rider_id": serializers.IntegerField(required=False),
            },
        ),
        responses={201: DetailSerializer, 400: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
    )
    def post(self, request):
        AvatarChangeRequest.expire_stale_requests()

        uploaded_file = request.FILES.get("image")
        try:
            _validate_avatar_image(uploaded_file)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        target_type = request.data.get("target_type", "account")

        if target_type == "account":
            if AvatarChangeRequest.objects.filter(
                target_account=request.user,
                status=AvatarChangeRequest.STATUS_PENDING,
            ).exists():
                return Response(
                    {"error": "Pro tvůj účet už čeká jedna žádost o avatar na schválení."},
                    status=status.HTTP_409_CONFLICT,
                )
            AvatarChangeRequest.objects.create(
                uploaded_by=request.user,
                target_account=request.user,
                image=uploaded_file,
            )
            return Response(
                {"detail": "Nový avatar účtu byl odeslán ke schválení administrátorem."},
                status=status.HTTP_201_CREATED,
            )

        if target_type == "rider":
            target_rider_id = request.data.get("target_rider_id")
            if not target_rider_id:
                return Response(
                    {"error": "Pole target_rider_id je povinné pro target_type == 'rider'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            rider = request.user.riders.filter(pk=target_rider_id, is_active=True).first()
            if not rider:
                return Response(
                    {"error": "Jezdec nenalezen nebo není navázán na tvůj účet."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if AvatarChangeRequest.objects.filter(
                target_rider=rider,
                status=AvatarChangeRequest.STATUS_PENDING,
            ).exists():
                return Response(
                    {"error": "Pro tohoto jezdce už čeká jedna žádost o avatar na schválení."},
                    status=status.HTTP_409_CONFLICT,
                )
            AvatarChangeRequest.objects.create(
                uploaded_by=request.user,
                target_rider=rider,
                image=uploaded_file,
            )
            return Response(
                {"detail": f"Nový avatar pro jezdce {rider.first_name} {rider.last_name} byl odeslán ke schválení."},
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"error": "Neplatný target_type. Povolen je 'account' nebo 'rider'."},
            status=status.HTTP_400_BAD_REQUEST,
        )


class RegisterAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [rest_throttling.ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=inline_serializer(
            name="RegisterRequest",
            fields={
                "email": serializers.EmailField(),
                "first_name": serializers.CharField(),
                "last_name": serializers.CharField(),
                "password": serializers.CharField(write_only=True, min_length=8),
            },
        ),
        responses={201: DetailSerializer, 400: ErrorSerializer, 409: ErrorSerializer},
    )
    def post(self, request):
        email_raw = request.data.get("email", "").strip()
        first_name = request.data.get("first_name", "").strip()
        last_name = request.data.get("last_name", "").strip()
        password = request.data.get("password", "")

        if not email_raw or not first_name or not last_name or not password:
            return Response(
                {"error": "Vyplň e-mail, jméno, příjmení a heslo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(password) < 8:
            return Response(
                {"error": "Heslo musí mít alespoň 8 znaků."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = normalize_account_email(email_raw)
        existing = Account.objects.filter(email__iexact=email).order_by("-date_joined").first()
        if existing:
            if not existing.is_active:
                return Response(
                    {"error": "Na tento e-mail čeká nedokončená registrace. Zažádej o nový aktivační e-mail."},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(
                {"error": "Uživatel s tímto e-mailem již existuje."},
                status=status.HTTP_409_CONFLICT,
            )

        user = Account.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        user.is_active = False
        user.save(update_fields=["is_active"])
        _send_activation_email_api(request, user)
        audit_logger.info("api_register_pending user_id=%s email=%s", user.pk, email)
        return Response(
            {"detail": "Registrace proběhla. Zkontroluj e-mail a aktivuj účet."},
            status=status.HTTP_201_CREATED,
        )


class ActivationResendAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=inline_serializer(
            name="ActivationResendRequest",
            fields={"email": serializers.EmailField()},
        ),
        responses={200: DetailSerializer, 400: ErrorSerializer, 410: ErrorSerializer},
    )
    def post(self, request):
        from django.conf import settings as django_settings
        email_raw = request.data.get("email", "").strip()
        if not email_raw:
            return Response({"error": "Zadej e-mail."}, status=status.HTTP_400_BAD_REQUEST)

        email = normalize_account_email(email_raw)
        user = Account.objects.filter(email__iexact=email).order_by("-date_joined").first()
        if not user or user.is_active:
            # Don't leak whether the account exists
            return Response({"detail": "Pokud účet čeká na aktivaci, pošleme nový e-mail."})

        max_age = timedelta(days=django_settings.ACCOUNT_PENDING_ACTIVATION_MAX_AGE_DAYS)
        if user.date_joined < timezone.now() - max_age:
            return Response(
                {"error": "Platnost registrace vypršela. Zaregistruj se znovu."},
                status=status.HTTP_410_GONE,
            )

        _send_activation_email_api(request, user)
        return Response({"detail": "Pokud účet čeká na aktivaci, pošleme nový e-mail."})


class PasswordResetRequestAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [rest_throttling.ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=inline_serializer(
            name="PasswordResetRequest",
            fields={"email": serializers.EmailField()},
        ),
        responses={200: DetailSerializer, 400: ErrorSerializer},
    )
    def post(self, request):
        from django.contrib.auth.forms import PasswordResetForm
        email = request.data.get("email", "").strip()
        if not email:
            return Response({"error": "Zadej e-mail."}, status=status.HTTP_400_BAD_REQUEST)

        form = PasswordResetForm({"email": email})
        if form.is_valid():
            form.save(
                request=request,
                use_https=request.is_secure(),
                email_template_name="registration/password_reset_email.html",
                subject_template_name="registration/password_reset_subject.txt",
            )
        # Always return 200 to avoid leaking whether an account exists
        return Response({"detail": "Pokud e-mail existuje, pošleme odkaz pro reset hesla."})


class PasswordResetConfirmAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=inline_serializer(
            name="PasswordResetConfirmRequest",
            fields={
                "uidb64": serializers.CharField(),
                "token": serializers.CharField(),
                "new_password": serializers.CharField(write_only=True, min_length=8),
            },
        ),
        responses={200: DetailSerializer, 400: ErrorSerializer},
    )
    def post(self, request):
        uidb64 = request.data.get("uidb64", "")
        token = request.data.get("token", "")
        new_password = request.data.get("new_password", "")

        if not uidb64 or not token or not new_password:
            return Response(
                {"error": "Chybí uidb64, token nebo nové heslo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {"error": "Heslo musí mít alespoň 8 znaků."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = Account.objects.get(pk=uid)
        except (Account.DoesNotExist, ValueError, TypeError):
            return Response({"error": "Neplatný odkaz."}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response({"error": "Odkaz je neplatný nebo vypršel."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=["password"])
        audit_logger.info("api_password_reset_confirm user_id=%s", user.pk)
        return Response({"detail": "Heslo bylo změněno. Přihlaš se."})

__all__ = ['LoginAPIView', 'LogoutAPIView', 'FcmTokenAPIView', 'MeAPIView', 'CreditTopUpAPIView', 'PasswordChangeAPIView', 'AvatarRequestAPIView', 'RegisterAPIView', 'ActivationResendAPIView', 'PasswordResetRequestAPIView', 'PasswordResetConfirmAPIView']
