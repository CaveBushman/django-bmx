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


class EntryAdminAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Entry.objects.all()
    serializer_class = EntrySerializer
    lookup_field = "transaction_id"
    permission_classes = [IsAdminUser]


class EventPublicDetailAPIView(generics.RetrieveAPIView):
    queryset = Event.objects.select_related("organizer").prefetch_related("photos")
    serializer_class = EventPublicSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]


class EventResultsAPIView(APIView):
    """Výsledky závodu seřazené podle kategorie a místa."""
    permission_classes = [AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        from event.models_results import Result

        get_object_or_404(Event, pk=pk)

        results = (
            Result.objects
            .filter(event_id=pk, is_beginner=False)
            .order_by('category', 'place')
        )

        categories_map = {}
        for r in results:
            cat = r.category or 'Bez kategorie'
            if cat not in categories_map:
                categories_map[cat] = []
            categories_map[cat].append({
                'place': r.place,
                'first_name': r.first_name or '',
                'last_name': r.last_name or '',
                'club': r.club or '',
                'uci_id': r.rider_id,
                'points': r.points,
                'is_20': r.is_20,
            })

        return Response({
            'event_id': pk,
            'categories': [
                {'category': cat, 'results': rows}
                for cat, rows in categories_map.items()
            ],
        })


class ResultListAPIView(generics.ListAPIView):
    """Verzovaný výsledkový feed pro mobilní aplikaci a externí integrace."""
    serializer_class = ResultPublicSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "first_name",
        "last_name",
        "club",
        "category",
        "event__name",
        "event__organizer__team_name",
    ]
    ordering_fields = [
        "date",
        "place",
        "points",
        "category",
        "last_name",
        "event_id",
    ]
    ordering = ["-date", "-event_id", "category", "place", "last_name", "first_name", "id"]

    def get_queryset(self):
        queryset = (
            Result.objects
            .select_related("event", "event__organizer", "rider", "rider__club")
        )

        event_pk = self.kwargs.get("pk")
        if event_pk is not None:
            get_object_or_404(Event, pk=event_pk)
            queryset = queryset.filter(event_id=event_pk)

        params = self.request.query_params
        if year := params.get("year"):
            queryset = queryset.filter(Q(date__year=year) | Q(event__date__year=year))
        if event_id := params.get("event"):
            queryset = queryset.filter(event_id=event_id)
        if uci_id := (params.get("uci_id") or params.get("rider")):
            queryset = queryset.filter(rider_id=uci_id)
        if category := params.get("category"):
            queryset = queryset.filter(category__iexact=category)
        if club := params.get("club"):
            queryset = queryset.filter(club__icontains=club)
        if event_type := (params.get("event_type") or params.get("type_for_ranking")):
            queryset = queryset.filter(Q(event__type_for_ranking=event_type) | Q(event_type=event_type))

        is_20 = _query_bool(params.get("is_20"))
        if is_20 is not None:
            queryset = queryset.filter(is_20=is_20)

        is_24 = _query_bool(params.get("is_24"))
        if is_24 is True:
            queryset = queryset.filter(is_20=False, is_beginner=False)
        elif is_24 is False:
            queryset = queryset.exclude(is_20=False, is_beginner=False)

        is_beginner = _query_bool(params.get("is_beginner"))
        if is_beginner is not None:
            queryset = queryset.filter(is_beginner=is_beginner)

        return queryset


class EventEntryRidersAPIView(APIView):
    """Přihlášení jezdci na závod — JSON verze pro mobilní aplikaci."""
    permission_classes = [AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT)
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

    @extend_schema(
        parameters=[
            OpenApiParameter("rider_uci_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: ErrorSerializer, 404: ErrorSerializer},
    )
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

    @extend_schema(
        request=inline_serializer(
            name="EventEnterRequest",
            fields={
                "rider_uci_id": serializers.IntegerField(),
                "is_20": serializers.BooleanField(default=False),
                "is_24": serializers.BooleanField(default=False),
                "is_beginner": serializers.BooleanField(default=False),
            },
        ),
        responses={
            201: EntryDetailSerializer,
            400: ErrorSerializer,
            402: inline_serializer(
                name="InsufficientCreditError",
                fields={
                    "error": serializers.CharField(),
                    "required": serializers.IntegerField(),
                    "balance": serializers.IntegerField(),
                },
            ),
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
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

    @extend_schema(request=None, responses={200: BalanceSerializer, 400: ErrorSerializer})
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

__all__ = ['EventList', 'EventDetail', 'EntryAdminAPIView', 'EventPublicDetailAPIView', 'EventResultsAPIView', 'ResultListAPIView', 'EventEntryRidersAPIView', 'EventEntryInfoAPIView', 'EventEnterAPIView', 'MyEntriesAPIView', 'EntryCancelAPIView']
