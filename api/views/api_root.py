"""Rozcestník API — co na tomhle serveru bydlí a kde.

Do Event Control (a do každého dalšího klienta kontraktu) se zadává **jediná
adresa**: ``https://<server>/api``. Zbytek cesty si klient doplní sám, takže
obsluze stačí jedna věta a stejná napříč weby a databázemi, ze kterých se
integruje. Aby ta adresa nebyla místem, které mlčí, odpovídá tady rozcestník:
kde je kontrakt Rider Registration API v1, kde mobilní API a jaká je verze.

Vzniklo 18. 8. 2026 poté, co se v nastavení objevila adresa ``…/api/v1`` —
mobilní API, které na ``/riders/`` odpoví 200 a holým polem. Vypadalo to jako
funkční spojení a přitom se nikdy nic nestáhlo; kdo si tehdy adresu otevřel
v prohlížeči, dostal chybovou stránku webu a nedozvěděl se nic.

Rozcestník je **veřejný a jen popisný** — vypisuje cesty, ne data. Kdo chce
jezdce, projde autentizací na příslušném endpointu jako dřív.
"""

from django.urls import reverse
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

# Verze kontraktu, kterou tenhle server vydává. Drží se u rozcestníku schválně:
# klient se má dozvědět, čemu tu bude rozumět, ještě než se začne autentizovat.
CONTRACT_SCHEMA_VERSION = "1.0"


def _contract_endpoints(request) -> tuple[str, dict]:
    """Kořen kontraktu a jeho cesty jako absolutní adresy.

    Kód závodu zůstává zástupným ``{race_code}`` — je to popis cesty, ne odkaz;
    přes ``reverse()`` by se složené závorky zakódovaly na ``%7B%7D`` a
    v dokumentaci by z toho byl nesmysl.
    """
    root = request.build_absolute_uri(reverse("registration_api:root")).rstrip("/")
    return root, {
        "riders": f"{root}/v1/riders",
        "clubs": f"{root}/v1/clubs",
        "registrations": f"{root}/v1/events/{{race_code}}/registrations",
    }


class _DescriptiveView(APIView):
    """Společný základ: veřejné, bez autentizace, bez omezení počtu dotazů.

    Odpověď je konstantní a nesahá do databáze, takže na ni nemá smysl pouštět
    anonymní limit — jediné, co by způsobil, je 429 zrovna ve chvíli, kdy si
    někdo ověřuje, proč mu integrace nejede.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []


class ApiRootAPIView(_DescriptiveView):
    """``GET /api/`` — co je na serveru za API a kde začíná."""

    @extend_schema(
        responses={200: None},
        description="Rozcestník API serveru — kořeny jednotlivých API a jejich verze.",
    )
    def get(self, request):
        root, endpoints = _contract_endpoints(request)
        return Response(
            {
                "service": "Czech BMX",
                "apis": {
                    "rider_registration": {
                        "schema_version": CONTRACT_SCHEMA_VERSION,
                        "root": root,
                        "endpoints": endpoints,
                        "note": (
                            "Kontrakt pro Event Control. Do nastavení integrace "
                            "patří kořen API serveru, tedy tahle adresa bez další "
                            "cesty; podstrom i verzi si klient doplní sám."
                        ),
                    },
                    "mobile": {
                        "root": request.build_absolute_uri("/api/v1/"),
                        "note": (
                            "API mobilní aplikace. Jiný tvar odpovědí než kontrakt "
                            "Rider Registration — pro Event Control se nepoužívá."
                        ),
                    },
                },
            }
        )


class RegistrationApiRootAPIView(_DescriptiveView):
    """``GET /api/registration/`` — kořen kontraktu sám za sebe.

    Kdo sem trefí, má adresu správně; ať se to dozví rovnou, místo aby to
    poznal až podle toho, že stahování skončí bez chyby a bez jezdců.
    """

    @extend_schema(
        responses={200: None},
        description="Kořen kontraktu Rider Registration API v1 na tomhle serveru.",
    )
    def get(self, request):
        root, endpoints = _contract_endpoints(request)
        return Response(
            {
                "contract": "rider-registration",
                "schema_version": CONTRACT_SCHEMA_VERSION,
                "root": root,
                "endpoints": endpoints,
            }
        )


__all__ = ["ApiRootAPIView", "RegistrationApiRootAPIView", "CONTRACT_SCHEMA_VERSION"]
