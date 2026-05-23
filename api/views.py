from django.contrib.auth import authenticate, get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status, filters
from rest_framework.permissions import IsAdminUser, IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from rider.models import Rider, ForeignRider
from event.models import Event, Entry
from news.models import News
from club.models import Club
from rider.serializers import RiderSerializer, ForeignRiderSerializer
from event.serializers import EventSerializer, EntrySerializer
from news.serializer import NewsSerializer
from club.serializers import ClubSerializer
from accounts.models import normalize_account_email


def _user_payload(user):
    return {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "credit": user.credit,
        "is_staff": user.is_staff,
        "is_rider": user.is_rider,
        "is_commissar": user.is_commissar,
        "is_trainer": user.is_trainer,
        "is_club_manager": user.is_club_manager,
        "photo_url": user.photo_url,
    }


# ---------------------------------------------------------------------------
# Riders
# ---------------------------------------------------------------------------

class RiderList(generics.ListAPIView):
    queryset = Rider.objects.filter(is_active=True).select_related("club")
    serializer_class = RiderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["club", "class_20", "class_24", "is_20", "is_24", "is_elite", "gender"]
    search_fields = ["first_name", "last_name", "uci_id", "plate_text"]
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
    serializer_class = ClubSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["team_name"]
    ordering_fields = ["team_name"]
    ordering = ["team_name"]


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class EventList(generics.ListAPIView):
    queryset = Event.objects.all().order_by("-date")
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
    queryset = News.objects.all().order_by("-created")
    serializer_class = NewsSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title"]
    ordering_fields = ["created"]
    ordering = ["-created"]


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
        user.save(update_fields=list(data.keys()))
        return Response(_user_payload(user))


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
