"""API pro BMX Event Control — přihlášky na závod + master data jezdců a klubů.

Připojení se v BMX Event Control nastavuje ve dvou místech:

* nastavení organizace — server (``https://<domena>/api/v1/event-control/``),
  username a password (``Club.event_control_*``, generuje se v adminu klubu),
* nastavení závodu — kód závodu (``Event.event_code``, vidět v adminu závodu).

Dvě úrovně oprávnění, obojí HTTP Basic (staff účet přes session/JWT projde také,
aby se integrace dala ověřit z prohlížeče):

* **údaje organizace** — přihlášky ke *vlastním* závodům pořadatele,
* **centrální údaje** ze settings (``EVENT_CONTROL_CENTRAL_*``) — celofederační
  master data jezdců a klubů pro centrální Event Control Admin **a přihlášky
  k libovolnému závodu**.

Centrální údaje platí na přihlášky od 15. 8. 2026. Do té doby na ně platily jen
údaje organizace, takže Event Control, který se centrálními údaji synchronizuje
registr, dostal na přihlášky 401 a pořadatel musel vyplňovat druhý pár údajů jen
kvůli nim. Kdo zná centrální heslo, čte stejně celý registr federace — přihlášky
jednoho závodu tím nejsou širší přístup, jen konzistentní.

Endpointy jsou ve dvou tvarech se stejnými daty i stejnou autentizací:

* ``event-control/…`` — původní tvar, který zná mobilní aplikace i starší
  instalace Event Control (jezdec se seznamem startů),
* ``v1/…`` — **obecný kontrakt Rider Registration API v1** (jedna registrace
  je jeden start). Event Control umí tenhle a jen tenhle, takže si nemusí
  držet zvláštní dialekt pro každý registrační systém; popis kontraktu je
  v Event Control v ``docs/RIDER_REGISTRATION_API.md``.

Všechno kromě jedné věci jen **vydává** data. Tou výjimkou je
``PATCH v1/riders/{uci_id}`` (část 3 kontraktu): trvalá výměna čipu u rampy je
oprava údaje, který vede web, a bez zápisu zpět by ji nejbližší synchronizace
přepsala zpátky na starou hodnotu. Zapisovat smí jen centrální údaje federace —
kdo odbavuje svůj závod, nemá tím právo měnit registr všem.
"""

import base64
import binascii
import logging
import secrets
import uuid

from django.conf import settings
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import throttling
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import Event
from event.services import registration_api_v1, registration_api_writeback
from event.services.event_control import (
    authenticate_club,
    build_entries_payload,
    club_can_access_event,
    event_payload,
    touch_club_access,
)
from event.services.event_control_sync import DEFAULT_PAGE_SIZE, clubs_page, riders_page

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")

WWW_AUTHENTICATE = 'Basic realm="BMX Event Control", charset="UTF-8"'


def decode_basic_credentials(request):
    """Rozparsuje hlavičku ``Authorization: Basic``. Vrací ``(username, password)``.

    ``(None, None)`` znamená, že Basic hlavička není poslaná; poškozená hlavička
    vede na ``AuthenticationFailed``.
    """
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.lower().startswith("basic "):
        return None, None
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1].strip()).decode("utf-8")
    except (binascii.Error, IndexError, UnicodeDecodeError, ValueError):
        raise AuthenticationFailed(_("Neplatná hlavička Authorization."))
    username, separator, password = decoded.partition(":")
    if not separator:
        raise AuthenticationFailed(_("Neplatná hlavička Authorization."))
    return username, password


class EventControlThrottle(throttling.SimpleRateThrottle):
    """Limit na organizaci (username), ne na IP — Event Control se dotazuje často."""

    scope = "event_control"

    def get_cache_key(self, request, view):
        try:
            username, _password = decode_basic_credentials(request)
        except AuthenticationFailed:
            username = None
        ident = username or self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class EventControlBaseView(APIView):
    """Sdílená Basic autentizace + autorizace na pořadatele závodu."""

    permission_classes = [AllowAny]
    throttle_classes = [EventControlThrottle]

    def get_authenticate_header(self, request):
        # Aby 401 odpověď řekla klientovi, že se čeká Basic auth organizace.
        return WWW_AUTHENTICATE

    def resolve_club(self, request):
        """Vrátí organizaci z Basic údajů, nebo ``None`` pro centrální/staff přístup.

        ``None`` znamená „bez omezení na pořadatele" — stejně jako u staff účtu.
        """
        username, password = decode_basic_credentials(request)
        if username is None:
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated and user.is_staff:
                return None
            raise AuthenticationFailed(_("Chybí přístupové údaje organizace."))

        # Centrální údaje federace platí i na přihlášky. Do 15. 8. 2026 platily
        # jen na master data, takže Event Control, který se jimi normálně
        # synchronizuje, dostal na přihlášky 401 — a pořadatel musel vyplňovat
        # druhý pár údajů jen kvůli nim. Kdo zná centrální heslo, vidí stejně
        # celý registr federace; přihlášky jednoho závodu nejsou širší přístup.
        if authenticate_central(username, password):
            audit_logger.info("event_control_central_access username=%s", username)
            return None

        club = authenticate_club(username, password)
        if club is None:
            audit_logger.warning("event_control_auth_failed username=%s", username)
            raise AuthenticationFailed(_("Neplatné přístupové údaje organizace."))
        return club

    def get_event(self, request, event_code):
        club = self.resolve_club(request)
        event = Event.objects.select_related("organizer").filter(event_code=event_code).first()
        if event is None:
            # Neexistující kód nesmí prozradit nic o jiných závodech.
            raise PermissionDenied(_("Závod s tímto kódem neexistuje nebo k němu nemáte přístup."))
        if club is not None:
            if not club_can_access_event(club, event):
                audit_logger.warning(
                    "event_control_event_forbidden club_id=%s event_id=%s", club.id, event.id
                )
                raise PermissionDenied(_("Závod s tímto kódem neexistuje nebo k němu nemáte přístup."))
            touch_club_access(club)
        return event


class EventControlPingAPIView(EventControlBaseView):
    """Test připojení pro nastavení organizace v BMX Event Control."""

    @extend_schema(
        responses={200: None},
        description="Ověření serveru a přístupových údajů organizace (HTTP Basic).",
    )
    def get(self, request):
        club = self.resolve_club(request)
        if club is None:
            # Bez organizace se sem dá dostat dvěma cestami a test připojení
            # nesmí tvrdit „staff", když volal centrální Event Control.
            username, password = decode_basic_credentials(request)
            central = username is not None and authenticate_central(username, password)
            return Response({
                "status": "ok",
                "organization": None,
                "central": central,
                "staff": not central,
            })
        touch_club_access(club)
        events = (
            Event.objects.filter(organizer=club)
            .order_by("-date")
            .values_list("name", "date", "event_code")[:10]
        )
        return Response({
            "status": "ok",
            "organization": club.team_name,
            "organization_id": club.id,
            "events": [
                {"name": name, "date": date.isoformat() if date else None, "code": str(code)}
                for name, date, code in events
            ],
        })


class EventControlEventAPIView(EventControlBaseView):
    """Metadata závodu podle kódu závodu."""

    @extend_schema(responses={200: None}, description="Detail závodu podle kódu závodu.")
    def get(self, request, event_code):
        event = self.get_event(request, event_code)
        return Response(event_payload(event))


class EventControlEntriesAPIView(EventControlBaseView):
    """Seznam přihlášených jezdců k importu do BMX Event Control."""

    @extend_schema(
        responses={200: None},
        description=(
            "Přihlášení jezdci závodu (domácí i zahraniční). Výchozí filtr jsou "
            "zaplacené a neodhlášené přihlášky, `?include_unpaid=1` přidá i nezaplacené."
        ),
    )
    def get(self, request, event_code):
        event = self.get_event(request, event_code)
        include_unpaid = _query_flag(request, "include_unpaid")
        payload = build_entries_payload(event, include_unpaid=include_unpaid)
        audit_logger.info(
            "event_control_entries_exported event_id=%s riders=%s include_unpaid=%s",
            event.id,
            payload["count"],
            include_unpaid,
        )
        return Response(payload)


def _query_flag(request, name) -> bool:
    return request.query_params.get(name, "").lower() in {"1", "true", "yes"}


def _query_int(request, name, default):
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({name: _("Musí být celé číslo.")})


def _query_updated_since(request):
    raw = request.query_params.get("updated_since")
    if not raw:
        return None
    parsed = parse_datetime(raw) or parse_date(raw)
    if parsed is None:
        raise ValidationError({"updated_since": _("Očekávaný formát je ISO 8601 (2026-05-01 nebo 2026-05-01T10:00:00).")})
    return parsed


def authenticate_central(username, password) -> bool:
    """Ověří přístupové údaje centrální instance Event Control Admin ze settings."""
    expected_username = getattr(settings, "EVENT_CONTROL_CENTRAL_USERNAME", "") or ""
    expected_password = getattr(settings, "EVENT_CONTROL_CENTRAL_PASSWORD", "") or ""
    if not expected_username or not expected_password:
        return False
    username_ok = secrets.compare_digest(str(username), expected_username)
    password_ok = secrets.compare_digest(str(password), expected_password)
    return username_ok and password_ok


class EventControlMasterDataBaseView(EventControlBaseView):
    """Výdej master dat (jezdci, kluby) pro centrální databázi Event Control Admin.

    Jde o celofederační data, proto sem nepouštíme přístupové údaje jednotlivých
    organizací — jen centrální údaje ze settings, nebo přihlášený staff účet.
    """

    def authorize_central(self, request):
        username, password = decode_basic_credentials(request)
        if username is None:
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated and user.is_staff:
                return
            raise AuthenticationFailed(_("Chybí centrální přístupové údaje."))
        if not authenticate_central(username, password):
            audit_logger.warning("event_control_central_auth_failed username=%s", username)
            raise AuthenticationFailed(_("Neplatné centrální přístupové údaje."))

    def page_params(self, request):
        return {
            "updated_since": _query_updated_since(request),
            "limit": _query_int(request, "limit", DEFAULT_PAGE_SIZE),
            "offset": _query_int(request, "offset", 0),
            "include_inactive": _query_flag(request, "include_inactive"),
        }


class RegistrationsV1APIView(EventControlBaseView):
    """Přihlášky závodu podle obecného kontraktu Rider Registration API v1.

    Stejná data i stejná autentizace jako ``event-control/…/entries/``, jen
    v provider-neutrálním tvaru: **jedna registrace je jeden start**, ne jeden
    jezdec. Ten rozdíl je celý smysl endpointu — závodní software přiděluje
    jednu kategorii na start, takže seznam startů uvnitř jezdce by musel
    rozbalovat každý konzument zvlášť.
    """

    @extend_schema(
        responses={200: None},
        description=(
            "Přihlášky závodu v obecném kontraktu v1, jeden záznam na start. "
            "Stránkování `?page=&page_size=`, `?include_unpaid=1` přidá nezaplacené."
        ),
    )
    def get(self, request, race_code):
        event = self.get_event(request, self._as_event_code(race_code))
        payload = registration_api_v1.registrations_page(
            event,
            page=_query_int(request, "page", 1),
            page_size=_query_int(request, "page_size", DEFAULT_PAGE_SIZE),
            include_unpaid=_query_flag(request, "include_unpaid"),
        )
        audit_logger.info(
            "registration_api_v1_exported event_id=%s page=%s count=%s",
            event.id,
            payload["page"],
            payload["count"],
        )
        return Response(payload)

    @staticmethod
    def _as_event_code(race_code):
        """Kód závodu z cesty na UUID.

        Kontrakt nechává ``api_race_code`` volným řetězcem, protože jiný
        poskytovatel může mít jiný tvar klíče. Tady je to UUID, takže překlep
        v nastavení závodu musí skončit stejnou odpovědí jako neexistující
        závod — ne chybou 500 a ne prozrazením, že kód sice existuje, ale
        patří někomu jinému.
        """
        try:
            return uuid.UUID(str(race_code))
        except (AttributeError, TypeError, ValueError):
            raise PermissionDenied(_("Závod s tímto kódem neexistuje nebo k němu nemáte přístup."))


class RidersV1APIView(EventControlMasterDataBaseView):
    """Jezdci pro centrální registr podle obecného kontraktu v1."""

    @extend_schema(
        responses={200: None},
        description=(
            "Jezdci v obecném kontraktu v1. Přírůstkově přes `?updated_since=`, "
            "stránkování `?limit=&offset=`."
        ),
    )
    def get(self, request):
        self.authorize_central(request)
        payload = registration_api_v1.riders_page(**self.page_params(request))
        audit_logger.info(
            "registration_api_v1_riders_exported count=%s returned=%s",
            payload["count"],
            len(payload["results"]),
        )
        return Response(payload)


class ClubsV1APIView(EventControlMasterDataBaseView):
    """Kluby pro centrální registr podle obecného kontraktu v1."""

    @extend_schema(
        responses={200: None},
        description=(
            "Kluby v obecném kontraktu v1. Přírůstkově přes `?updated_since=`, "
            "stránkování `?limit=&offset=`."
        ),
    )
    def get(self, request):
        self.authorize_central(request)
        payload = registration_api_v1.clubs_page(**self.page_params(request))
        audit_logger.info(
            "registration_api_v1_clubs_exported count=%s returned=%s",
            payload["count"],
            len(payload["results"]),
        )
        return Response(payload)


class RiderChipV1APIView(EventControlMasterDataBaseView):
    """Zápis trvalé změny čipu od Event Control — kontrakt v1, část 3.

    Jediný endpoint kontraktu, který data **mění**, a proto jediný za
    centrálními údaji federace i pro zápis: čip jezdce je celofederační údaj,
    ne majetek jednoho pořadatele. Údaje organizace sem schválně nepustíme —
    kdo odbavuje svůj závod, nemá tím právo měnit registr všem.

    Bez tohohle endpointu je oprava čipu u rampy jednorázová: Event Control ji
    má ve svém registru, ale při nejbližší synchronizaci ji stažená hodnota
    z webu přepíše zpátky na starou.
    """

    @extend_schema(
        request=None,
        responses={200: None},
        description=(
            "Trvalá změna čipu jezdce od BMX Event Control. Tělo obsahuje "
            "`chip_id_20` nebo `chip_id_24`; prázdný řetězec čip odebere. "
            "Idempotentní — stejný čip podruhé projde a nic nezmění."
        ),
    )
    def patch(self, request, uci_id):
        self.authorize_central(request)
        payload = dict(request.data or {})
        # UCI ID z cesty je závazné. Kdyby rozhodovalo tělo, dal by se jedním
        # požadavkem změnit čip někomu jinému, než na koho míří adresa.
        payload["uci_id"] = uci_id
        try:
            rider, changes = registration_api_writeback.apply_chip_change(payload)
        except registration_api_writeback.ChipWritebackError as exc:
            audit_logger.warning(
                "event_control_chip_writeback_refused uci_id=%s status=%s reason=%s",
                uci_id,
                exc.status,
                exc.message,
            )
            return Response({"detail": exc.message}, status=exc.status)
        return Response(registration_api_writeback.response_payload(rider, changes))


class EventControlRidersAPIView(EventControlMasterDataBaseView):
    """Přírůstkový výdej jezdců pro centrální databázi jezdců."""

    @extend_schema(
        responses={200: None},
        description=(
            "Jezdci pro synchronizaci s Event Control Admin. Přírůstkově přes "
            "`?updated_since=`, stránkování `?limit=&offset=`, `?include_inactive=1` "
            "přidá neaktivní a neschválené."
        ),
    )
    def get(self, request):
        self.authorize_central(request)
        payload = riders_page(**self.page_params(request))
        audit_logger.info(
            "event_control_riders_exported count=%s returned=%s", payload["count"], len(payload["results"])
        )
        return Response(payload)


class EventControlClubsAPIView(EventControlMasterDataBaseView):
    """Přírůstkový výdej klubů pro centrální databázi klubů."""

    @extend_schema(
        responses={200: None},
        description=(
            "Kluby pro synchronizaci s Event Control Admin. Přírůstkově přes "
            "`?updated_since=`, stránkování `?limit=&offset=`."
        ),
    )
    def get(self, request):
        self.authorize_central(request)
        payload = clubs_page(**self.page_params(request))
        audit_logger.info(
            "event_control_clubs_exported count=%s returned=%s", payload["count"], len(payload["results"])
        )
        return Response(payload)
