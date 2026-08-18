"""Obecný kontrakt Rider Registration API — vlastní URL strom.

Kontrakt (popsaný v Event Control v ``docs/RIDER_REGISTRATION_API.md``) žádá
cesty ``{base_url}/v1/riders``, ``{base_url}/v1/clubs`` a
``{base_url}/v1/events/{kód}/registrations``. Do ``api/urls.py`` se nevešly:
ten je celý namountovaný na ``/api/v1/`` a už tam ``riders/`` i ``clubs/``
obsluhují mobilní aplikaci. Dva různé tvary odpovědi rozlišené jedním
lomítkem jsou past, do které jednou spadne každý.

Vlastní strom na ``/api/registration/`` proto dává přesně ty cesty, které
kontrakt předepisuje. Mobilní API se nemění.

Do nastavení integrace se přitom zadává jen **kořen API serveru**:

    base_url = https://<domena>/api

a podstrom ``registration`` i verzi si klient doplní sám (od 18. 8. 2026; viz
``docs/BMX_EVENT_CONTROL.md``). Jedna adresa napříč weby a databázemi je jediné,
co jde obsluze říct jednou větou — a `/api` samo odpovídá rozcestníkem
(``api/views/api_root.py``), takže se dá otevřít v prohlížeči a ověřit.
"""

from django.urls import path

from api.views.api_root import RegistrationApiRootAPIView
from api.views.event_control import (
    ClubsV1APIView,
    RegistrationsV1APIView,
    RiderChipV1APIView,
    RidersV1APIView,
)

app_name = "registration_api"

urlpatterns = [
    # Kořen kontraktu odpovídá sám za sebe — kdo sem trefí, má adresu správně
    # a nemusí to poznávat podle toho, že mu stahování skončí bez jezdců.
    path("", RegistrationApiRootAPIView.as_view(), name="root"),
    path("v1/riders", RidersV1APIView.as_view(), name="v1-riders"),
    path("v1/clubs", ClubsV1APIView.as_view(), name="v1-clubs"),
    path(
        "v1/events/<str:race_code>/registrations",
        RegistrationsV1APIView.as_view(),
        name="v1-registrations",
    ),
    # Část 3 kontraktu — zápis trvalé změny čipu od Event Control. Kolize
    # s výdejem seznamu nehrozí: `<str:uci_id>` neodpovídá prázdnému úseku,
    # takže `v1/riders/` dopadne dál na `RidersV1APIView`.
    path("v1/riders/<str:uci_id>", RiderChipV1APIView.as_view(), name="v1-rider-chip"),
    path("v1/riders/<str:uci_id>/", RiderChipV1APIView.as_view(), name="v1-rider-chip-slash"),
    # Kontrakt cesty bez lomítka; klient, který ho přesto pošle, nemá dostat
    # přesměrování s Basic hlavičkou navíc, ale rovnou odpověď.
    path("v1/riders/", RidersV1APIView.as_view(), name="v1-riders-slash"),
    path("v1/clubs/", ClubsV1APIView.as_view(), name="v1-clubs-slash"),
    path(
        "v1/events/<str:race_code>/registrations/",
        RegistrationsV1APIView.as_view(),
        name="v1-registrations-slash",
    ),
]
