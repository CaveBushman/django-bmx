"""Jednotný formát chybových odpovědí API.

Mobilní klient potřebuje předvídatelný tvar chyby. DRF ve výchozím stavu vrací
různé tvary: ``{"detail": "..."}`` (auth, 404, throttle), field-keyed validační
chyby ``{"pole": ["..."]}`` a vlastní views ``{"error": "..."}``.

Tento handler ke každé chybové odpovědi (vyvolané výjimkou) **přidá** klíč
``error`` se srozumitelnou zprávou jako string — aniž by odebíral původní data
(``detail`` i field chyby zůstávají). Klient se tak může spolehnout, že každá
chybová odpověď má vždy ``error``."""

from rest_framework.views import exception_handler as drf_exception_handler


def _first_field_message(data):
    """Z field-keyed dict (např. {'email': ['…']}) vytáhne první čitelnou zprávu."""
    for key, value in data.items():
        if isinstance(value, (list, tuple)) and value:
            return f"{key}: {value[0]}"
        if isinstance(value, str):
            return f"{key}: {value}"
    return "Neplatný požadavek."


def _extract_message(data):
    if isinstance(data, dict):
        if "error" in data and isinstance(data["error"], str):
            return data["error"]
        if "detail" in data:
            return str(data["detail"])
        return _first_field_message(data)
    if isinstance(data, (list, tuple)) and data:
        return str(data[0])
    return str(data)


def api_exception_handler(exc, context):
    """DRF exception handler, který doplní konzistentní klíč ``error``."""
    response = drf_exception_handler(exc, context)
    if response is None:
        # Nezachycená výjimka (500) — DRF ji nechává projít, neřešíme tvar zde.
        return None

    message = _extract_message(response.data)
    if isinstance(response.data, dict):
        # Aditivně — nepřepisujeme existující detail/field chyby.
        response.data.setdefault("error", message)
    else:
        # List/string → zabalíme do dictu, původek zachováme v detail.
        response.data = {"error": message, "detail": response.data}
    return response
