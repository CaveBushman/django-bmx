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
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django_filters.rest_framework import DjangoFilterBackend
from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError, features
from rest_framework import generics, status, filters
from bmx.search_filters import NormalizedSearchFilter
from rest_framework.permissions import IsAdminUser, IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from rider.models import Rider, ForeignRider
from rider.rider import get_rider_data
from rider.plates import generate_available_plate_values, normalize_plate_value, legacy_plate_int, display_plate
from event.models import CreditTransaction, Event, Entry
from event.models_events import Event as EventModel
from news.models import News
from club.models import Club
from rider.serializers import RiderSerializer, ForeignRiderSerializer
from event.serializers import EventSerializer, EntrySerializer, EventPublicSerializer, EntryDetailSerializer
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
    final_size = int(getattr(settings, "AVATAR_FINAL_IMAGE_SIZE", 512))
    output_quality = int(getattr(settings, "AVATAR_FINAL_IMAGE_QUALITY", 86))
    preferred_format = "WEBP" if features.check("webp") else "JPEG"
    extension = "webp" if preferred_format == "WEBP" else "jpg"
    original_truncated_setting = ImageFile.LOAD_TRUNCATED_IMAGES

    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.fit(
            image,
            (final_size, final_size),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        output = BytesIO()
        try:
            if preferred_format == "WEBP":
                image.save(output, format="WEBP", quality=output_quality, method=6)
            else:
                image.save(output, format="JPEG", quality=90, optimize=True)
        except (OSError, KeyError):
            output = BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
            extension = "jpg"
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = original_truncated_setting
        uploaded_file.seek(0)

    output.seek(0)
    filename = f"account-avatar-{user.pk}-{uuid.uuid4().hex[:12]}.{extension}"
    return filename, ContentFile(output.read())

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


def _user_payload(user):
    linked_rider = user.riders.filter(is_active=True).order_by("last_name", "first_name").first()
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
    }


# ---------------------------------------------------------------------------
# Riders
# ---------------------------------------------------------------------------

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
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, NormalizedSearchFilter, filters.OrderingFilter]
    filterset_fields = ["club", "class_20", "class_24", "is_20", "is_24", "is_elite", "gender"]
    search_fields = ["search_text_normalized", "=uci_id", "plate_text"]
    ordering_fields = ["last_name", "first_name", "uci_id"]
    ordering = ["last_name", "first_name"]


class RiderDetail(generics.RetrieveAPIView):
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer
    lookup_field = "uci_id"
    permission_classes = [IsAuthenticated]


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

    def get(self, request, uci_id):
        is_commissar = getattr(request.user, 'is_commissar', False)
        is_admin = (
            getattr(request.user, 'is_admin', False)
            or request.user.is_superuser
            or request.user.is_staff
        )
        if not (is_commissar or is_admin):
            return Response({"detail": "Permission denied."}, status=403)

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


# ---------------------------------------------------------------------------
# Foreign riders
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Clubs
# ---------------------------------------------------------------------------

class ClubList(generics.ListAPIView):
    queryset = Club.objects.filter(is_active=True)
    serializer_class = ClubPublicSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["team_name"]
    ordering_fields = ["team_name"]
    ordering = ["team_name"]


class ClubDetail(generics.RetrieveAPIView):
    queryset = Club.objects.filter(is_active=True)
    serializer_class = ClubPublicSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]


# ---------------------------------------------------------------------------
# Plate request (žádost o přidělení startovního čísla)
# ---------------------------------------------------------------------------

class PlateRequestFreePlatesAPIView(APIView):
    """Returns the ordered list of currently available plate numbers."""
    permission_classes = [AllowAny]

    def get(self, request):
        used = [
            display_plate(pt, p, fallback="")
            for pt, p in Rider.objects.filter(is_active=True).values_list("plate_text", "plate")
        ]
        return Response({"free_plates": generate_available_plate_values(used)})


class PlateRequestLookupAPIView(APIView):
    """Looks up a UCI ID against the Czech cycling federation and returns rider data."""
    permission_classes = [AllowAny]

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
            return Response(
                {"error": "Licence nebyla nalezena v databázi ČSC."},
                status=status.HTTP_404_NOT_FOUND,
            )
        gender_code = data_json.get("sex", {}).get("code", "M")
        return Response({
            "uci_id": uci_id,
            "first_name": data_json.get("firstName", "").strip(),
            "last_name": (data_json.get("lastName", "") or "").strip().capitalize(),
            "date_of_birth": (data_json.get("birth", "") or "")[:10],
            "gender": "Žena" if gender_code == "F" else "Muž",
        })


class PlateRequestAPIView(APIView):
    """Creates a new plate-number request (Rider with is_approved=False)."""
    permission_classes = [IsAuthenticated]

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


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class EventList(generics.ListAPIView):
    queryset = Event.objects.select_related("organizer").all().order_by("-date")
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["type_for_ranking"]
    search_fields = ["name", "city"]
    ordering_fields = ["date", "name"]
    ordering = ["-date"]

    def get_queryset(self):
        qs = super().get_queryset()
        year = self.request.query_params.get("year")
        if year:
            qs = qs.filter(date__year=year)
        return qs


class EventDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAdminUser]


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

class NewsListAPIView(generics.ListAPIView):
    queryset = News.objects.filter(published=True, publish_in_app=True).order_by("-created_date", "-id")
    serializer_class = NewsSerializer
    permission_classes = [AllowAny]
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title"]
    ordering_fields = ["created_date", "publish_date", "id"]
    ordering = ["-created_date", "-id"]


# ---------------------------------------------------------------------------
# Entry (admin)
# ---------------------------------------------------------------------------

class EntryAdminAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Entry.objects.all()
    serializer_class = EntrySerializer
    lookup_field = "transaction_id"
    permission_classes = [IsAdminUser]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

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

    def post(self, request):
        token = (request.data.get("fcm_token") or "").strip()
        if not token:
            return Response({"detail": "fcm_token required."}, status=status.HTTP_400_BAD_REQUEST)
        FcmDevice.objects.update_or_create(
            token=token,
            defaults={"user": request.user},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        token = (request.data.get("fcm_token") or "").strip()
        if token:
            FcmDevice.objects.filter(user=request.user, token=token).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_user_payload(request.user))

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


# ---------------------------------------------------------------------------
# Auth — registration & activation
# ---------------------------------------------------------------------------

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


class RegisterAPIView(APIView):
    permission_classes = [AllowAny]

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


# ---------------------------------------------------------------------------
# E-shop — catalogue (public)
# ---------------------------------------------------------------------------

class EshopCategoryListAPIView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]


class EshopProductListAPIView(generics.ListAPIView):
    serializer_class = ProductListSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["category__slug"]
    search_fields = ["name", "subtitle", "collection"]

    def get_queryset(self):
        return (
            Product.objects.filter(active=True)
            .select_related("category")
            .prefetch_related("variants")
        )


class EshopProductDetailAPIView(generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Product.objects.filter(active=True)
            .select_related("category")
            .prefetch_related("variants")
        )


# ---------------------------------------------------------------------------
# E-shop — cart (session-based, no auth required)
# ---------------------------------------------------------------------------

class EshopCartAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cart = Cart(request)
        variant_ids = cart.variant_ids()
        if not variant_ids:
            return Response({"items": [], "total": "0", "count": 0})

        variant_map = {
            v.pk: v
            for v in ProductVariant.objects.select_related("product").filter(
                pk__in=variant_ids, active=True
            )
        }

        items = []
        total = 0
        for vid in variant_ids:
            qty = cart.get_quantity(vid)
            variant = variant_map.get(vid)
            if not variant or qty <= 0:
                continue
            subtotal = variant.price * qty
            total += subtotal
            items.append({
                "variant_id": vid,
                "product_id": variant.product_id,
                "product_name": variant.product.name,
                "product_slug": variant.product.slug,
                "variant_label": variant.label,
                "price": str(variant.price),
                "quantity": qty,
                "stock": variant.stock,
                "subtotal": str(subtotal),
            })

        return Response({"items": items, "total": str(total), "count": len(items)})

    def post(self, request):
        try:
            variant_id = int(request.data.get("variant_id"))
            quantity = int(request.data.get("quantity", 1))
        except (TypeError, ValueError):
            return Response({"error": "Neplatná data."}, status=status.HTTP_400_BAD_REQUEST)

        if quantity < 0:
            return Response({"error": "Množství musí být kladné."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            variant = ProductVariant.objects.get(pk=variant_id, active=True)
        except ProductVariant.DoesNotExist:
            return Response({"error": "Varianta neexistuje."}, status=status.HTTP_404_NOT_FOUND)

        cart = Cart(request)
        action = request.data.get("action", "add")
        if action == "set":
            if quantity > variant.stock:
                return Response(
                    {"error": f"Na skladě je jen {variant.stock} ks."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cart.set(variant_id, quantity)
        else:
            new_qty = cart.get_quantity(variant_id) + quantity
            if new_qty > variant.stock:
                return Response(
                    {"error": f"Na skladě je jen {variant.stock} ks."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cart.add(variant_id, quantity)

        return Response({"ok": True, "quantity": cart.get_quantity(variant_id)})

    def delete(self, request):
        Cart(request).clear()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EshopCartItemAPIView(APIView):
    permission_classes = [AllowAny]

    def delete(self, request, variant_id):
        Cart(request).remove(variant_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# E-shop — checkout & orders (auth required)
# ---------------------------------------------------------------------------

class EshopCheckoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        cart = Cart(request)
        if not cart:
            return Response({"error": "Košík je prázdný."}, status=status.HTTP_400_BAD_REQUEST)

        variant_ids = cart.variant_ids()
        variant_map = {
            v.pk: v
            for v in ProductVariant.objects.select_related("product").filter(
                pk__in=variant_ids, active=True
            )
        }

        items = []
        for vid in variant_ids:
            qty = cart.get_quantity(vid)
            variant = variant_map.get(vid)
            if not variant:
                return Response(
                    {"error": f"Varianta #{vid} už není dostupná."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if qty > variant.stock:
                return Response(
                    {"error": f"{variant.product.name} / {variant.label} — nedostatek kusů na skladě."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            items.append({"variant": variant, "quantity": qty})

        first_name = request.data.get("first_name", "").strip()
        last_name = request.data.get("last_name", "").strip()
        email = request.data.get("email", "").strip()
        event_id = request.data.get("event")

        if not first_name or not last_name or not email:
            return Response(
                {"error": "Vyplň jméno, příjmení a e-mail."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not event_id:
            return Response({"error": "Vyber závod pro předání."}, status=status.HTTP_400_BAD_REQUEST)

        cutoff = timezone.localdate() + timedelta(days=5)
        try:
            event = EventModel.objects.get(
                pk=event_id,
                date__gte=cutoff,
                eshop_pickup_enabled=True,
            )
        except EventModel.DoesNotExist:
            return Response(
                {"error": "Vybraný závod není dostupný pro předání."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with db_tx.atomic():
                order = Order.objects.create(
                    user=request.user,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    phone=request.data.get("phone", ""),
                    street=request.data.get("street", ""),
                    city=request.data.get("city", ""),
                    zip_code=request.data.get("zip_code", ""),
                    note=request.data.get("note", ""),
                    event=event,
                )
                OrderHistory.record(
                    order=order,
                    action=OrderHistory.Action.CREATED,
                    actor=request.user,
                    note="Objednávka vytvořena přes API.",
                )
                for item in items:
                    OrderItem.objects.create(
                        order=order,
                        variant=item["variant"],
                        quantity=item["quantity"],
                        unit_price=item["variant"].price,
                    )
                order.charge_credits(actor=request.user)
                order.ensure_invoice_number(actor=request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        cart.clear()
        return Response(
            OrderSerializer(order, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class EshopOrderListAPIView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related("items__variant__product")
            .order_by("-created")
        )


class EshopOrderDetailAPIView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return Order.objects.filter(user=self.request.user).prefetch_related(
            "items__variant__product"
        )


class EshopOrderCancelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, user=request.user)
        try:
            order.cancel_by_user(actor=request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order, context={"request": request}).data)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

class RankingCategoryListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        categories = Categories.get_categories()
        return Response({"categories": categories})


class RankingAPIView(APIView):
    permission_classes = [AllowAny]

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


# ---------------------------------------------------------------------------
# Entry registration — přihlašování jezdců na závody
# ---------------------------------------------------------------------------

class EventPublicDetailAPIView(generics.RetrieveAPIView):
    queryset = Event.objects.select_related("organizer").prefetch_related("photos")
    serializer_class = EventPublicSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]


class EventEntryRidersAPIView(APIView):
    """Přihlášení jezdci na závod — JSON verze pro mobilní aplikaci."""
    permission_classes = [AllowAny]

    def get(self, request, pk):
        from event.models import Entry, EntryForeign
        from event.views.entry_helpers import build_public_entry_rows

        get_object_or_404(Event, pk=pk)

        czech_entries = Entry.objects.filter(event=pk, payment_complete=1, checkout=0).select_related("rider", "rider__club")
        foreign_entries = EntryForeign.objects.filter(event=pk, payment_complete=1, checkout=0).select_related("rider")
        czech_checkout = Entry.objects.filter(event=pk, payment_complete=1, checkout=1).select_related("rider", "rider__club")
        foreign_checkout = EntryForeign.objects.filter(event=pk, payment_complete=1, checkout=1).select_related("rider")

        def serialize_rows(rows):
            return [
                {
                    "first_name": r.first_name,
                    "last_name": r.last_name,
                    "category": r.category,
                    "club": r.club,
                    "uci_id": r.uci_id,
                    "plate": r.plate,
                    "photo_url": r.photo_url,
                    "is_foreign": r.is_foreign,
                }
                for r in sorted(rows, key=lambda x: (x.last_name, x.first_name))
            ]

        entries = build_public_entry_rows(czech_entries) + build_public_entry_rows(foreign_entries, is_foreign=True)
        checkout = build_public_entry_rows(czech_checkout) + build_public_entry_rows(foreign_checkout, is_foreign=True)

        return Response({
            "entries": serialize_rows(entries),
            "checkout": serialize_rows(checkout),
            "categories": sorted({r.category for r in entries if r.category}),
        })


class EventEntryInfoAPIView(APIView):
    """Vrátí dostupné kategorie a poplatky pro konkrétního jezdce na daném závodě."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        event = get_object_or_404(
            Event.objects.select_related("classes_and_fees_like"), pk=pk
        )
        uci_id = request.query_params.get("rider_uci_id")
        if not uci_id:
            return Response(
                {"error": "Parametr rider_uci_id je povinný."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            rider = Rider.objects.get(uci_id=int(uci_id), is_active=True, is_approved=True)
        except (Rider.DoesNotExist, ValueError):
            return Response(
                {"error": "Jezdec nenalezen."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from event.func import (
            is_registration_open,
            is_unregistration_open,
            get_unregistration_deadline,
        )
        from event.views.entry_helpers import (
            _resolve_rider_event_data,
            resolve_event_beginner_support,
        )
        from event.models import Entry as EventEntry

        already = {
            "is_beginner": False,
            "is_20": False,
            "is_24": False,
        }
        for entry in EventEntry.objects.filter(
            event=event, rider=rider, payment_complete=True, checkout=False
        ):
            if entry.is_beginner:
                already["is_beginner"] = True
            if entry.is_20:
                already["is_20"] = True
            if entry.is_24:
                already["is_24"] = True

        beginners_enabled = resolve_event_beginner_support(event)
        d = _resolve_rider_event_data(event, rider, beginners_enabled=beginners_enabled)

        deadline = get_unregistration_deadline(event)

        return Response({
            "event_id": event.pk,
            "event_name": event.name,
            "event_date": event.date,
            "registration_open": is_registration_open(event),
            "unregistration_open": is_unregistration_open(event),
            "unregistration_deadline": deadline,
            "rider_uci_id": rider.uci_id,
            "options": {
                "is_20": {
                    "allowed": d["allow_20"],
                    "class": d["class_20"] if d["allow_20"] else None,
                    "fee": d["fee_20"] if d["allow_20"] else 0,
                    "already_registered": already["is_20"],
                },
                "is_24": {
                    "allowed": d["allow_24"],
                    "class": d["class_24"] if d["allow_24"] else None,
                    "fee": d["fee_24"] if d["allow_24"] else 0,
                    "already_registered": already["is_24"],
                },
                "is_beginner": {
                    "allowed": d["allow_beginner"],
                    "class": d["class_beginner"] if d["allow_beginner"] else None,
                    "fee": d["fee_beginner"] if d["allow_beginner"] else 0,
                    "already_registered": already["is_beginner"],
                },
            },
        })


class EventEnterAPIView(APIView):
    """Přihlásí jezdce na závod a okamžitě strhne kredit."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        event = get_object_or_404(
            Event.objects.select_related("classes_and_fees_like"), pk=pk
        )

        from event.func import is_registration_open
        from event.views.entry_helpers import (
            _resolve_rider_event_data,
            resolve_event_beginner_support,
        )
        from event.views.payment_helpers import pay_orders_from_credit
        from event.models import Entry as EventEntry, DebetTransaction
        from event.credit import calculate_user_balance

        if not is_registration_open(event):
            return Response(
                {"error": "Registrace na tento závod není otevřena."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uci_id = request.data.get("rider_uci_id")
        is_20 = bool(request.data.get("is_20", False))
        is_24 = bool(request.data.get("is_24", False))
        is_beginner = bool(request.data.get("is_beginner", False))

        if not uci_id:
            return Response(
                {"error": "Pole rider_uci_id je povinné."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not (is_20 or is_24 or is_beginner):
            return Response(
                {"error": "Vyber alespoň jednu kategorii (is_20, is_24, nebo is_beginner)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if is_beginner and (is_20 or is_24):
            return Response(
                {"error": "Začátečník nemůže být současně přihlášen do is_20 nebo is_24."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            rider = Rider.objects.get(
                uci_id=int(uci_id),
                is_active=True,
                is_approved=True,
            )
        except (Rider.DoesNotExist, ValueError):
            return Response({"error": "Jezdec nenalezen."}, status=status.HTTP_404_NOT_FOUND)

        if not rider.valid_licence and not rider.fix_valid_licence:
            return Response(
                {"error": "Jezdec nemá platnou licenci."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        beginners_enabled = resolve_event_beginner_support(event)
        d = _resolve_rider_event_data(event, rider, beginners_enabled=beginners_enabled)

        # Validace kategorií
        if is_20 and not d["allow_20"]:
            return Response(
                {"error": f"Jezdec nemůže být přihlášen do kategorie 20\" ({d['class_20']})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if is_24 and not d["allow_24"]:
            return Response(
                {"error": f"Jezdec nemůže být přihlášen do kategorie 24\" ({d['class_24']})."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if is_beginner and not d["allow_beginner"]:
            return Response(
                {"error": "Jezdec nemůže být přihlášen jako začátečník."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Zkontroluj duplicitu
        category_flags = {"is_20": is_20, "is_24": is_24, "is_beginner": is_beginner}
        duplicate = EventEntry.objects.filter(
            event=event,
            rider=rider,
            payment_complete=True,
            checkout=False,
            **category_flags,
        ).exists()
        if duplicate:
            return Response(
                {"error": "Jezdec je na tento závod a kategorii již přihlášen."},
                status=status.HTTP_409_CONFLICT,
            )

        # Spočítej poplatek
        fee_20 = d["fee_20"] if is_20 else 0
        fee_24 = d["fee_24"] if is_24 else 0
        fee_beginner = d["fee_beginner"] if is_beginner else 0
        total_fee = fee_20 + fee_24 + fee_beginner

        user = request.user
        if user.credit < total_fee:
            return Response(
                {
                    "error": f"Nedostatek kreditu. Potřeba: {total_fee} Kč, zůstatek: {user.credit} Kč.",
                    "required": total_fee,
                    "balance": user.credit,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        with db_tx.atomic():
            # Smaž případnou starou nezaplacenou rezervaci pro stejnou kategorii
            EventEntry.objects.filter(
                event=event, rider=rider, payment_complete=False, **category_flags
            ).delete()

            entry = EventEntry.objects.create(
                user=user,
                event=event,
                rider=rider,
                is_20=is_20,
                is_24=is_24,
                is_beginner=is_beginner,
                class_20=d["class_20"] if is_20 else "",
                class_24=d["class_24"] if is_24 else "",
                class_beginner=d["class_beginner"] if is_beginner else "",
                fee_20=fee_20,
                fee_24=fee_24,
                fee_beginner=fee_beginner,
                payment_complete=True,
                customer_name=f"{user.first_name} {user.last_name}".strip(),
                customer_email=user.email,
            )
            if total_fee > 0:
                DebetTransaction.objects.create(
                    user=user,
                    entry=entry,
                    amount=total_fee,
                )
                user.credit = calculate_user_balance(user.id)
                user.save(update_fields=["credit"])

        return Response(
            EntryDetailSerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )


class MyEntriesAPIView(generics.ListAPIView):
    """Přihlášky přihlášeného uživatele na budoucí závody."""
    serializer_class = EntryDetailSerializer
    permission_classes = [IsAuthenticated]
    queryset = Event.objects.none()  # pro drf-spectacular

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            from event.models import Entry as EventEntry
            return EventEntry.objects.none()
        from event.models import Entry as EventEntry
        return (
            EventEntry.objects.filter(
                user=self.request.user,
                payment_complete=True,
                event__date__gte=timezone.now().date(),
            )
            .select_related("event", "rider")
            .order_by("event__date", "rider__last_name", "rider__first_name")
        )


class EntryCancelAPIView(APIView):
    """Storno přihlášky — odečtená částka se vrátí do kreditu."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from event.models import Entry as EventEntry, DebetTransaction
        from event.func import is_unregistration_open
        from event.credit import calculate_user_balance

        entry = get_object_or_404(
            EventEntry.objects.select_related("event", "rider"),
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
            DebetTransaction.objects.filter(user=user, entry=entry).delete()
            entry.delete()
            user.credit = calculate_user_balance(user.id)
            user.save(update_fields=["credit"])

        return Response(
            {"ok": True, "new_balance": user.credit},
            status=status.HTTP_200_OK,
        )


# ── Foreign rider entries ─────────────────────────────────────────────────────

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


class ForeignEventEntryInfoAPIView(APIView):
    """Vrátí info pro přihlášení zahraničního jezdce — lookup jezdce + dostupné kategorie."""
    permission_classes = [IsAuthenticated]

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
