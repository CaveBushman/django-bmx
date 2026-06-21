"""Bezpečná serializace JSON pro vkládání do HTML (`<script>` / `|safe`).

`json.dumps` neescapuje `<`, `>`, `&`, takže řetězec obsahující `</script>`
unikne z `<script>` bloku → XSS. `html_safe_json` zaescapuje tyto znaky (a
oddělovače řádků U+2028/U+2029, které lámou JS literály) na ``\\uXXXX``. Výsledek
je validní JSON i JS string – `JSON.parse` i přímé přiřazení ``var x = {...}`` ho
dekódují korektně a `</script>` se v HTML nikdy neobjeví.
"""

import json

# Znak (code-point) v JSON → jeho \uXXXX escape. Klíče zapsané jako Python
# escape sekvence, ať se U+2028/U+2029 (neviditelné) nezamění s mezerou.
_HTML_ESCAPES = (
    ("<", "\\u003c"),
    (">", "\\u003e"),
    ("&", "\\u0026"),
    (" ", "\\u2028"),
    (" ", "\\u2029"),
)


def html_safe_json(data, **dumps_kwargs):
    """Serializuje ``data`` do JSON bezpečného pro vložení do HTML/`<script>`."""
    dumps_kwargs.setdefault("ensure_ascii", False)
    dumped = json.dumps(data, **dumps_kwargs)
    for char, escaped in _HTML_ESCAPES:
        dumped = dumped.replace(char, escaped)
    return dumped
