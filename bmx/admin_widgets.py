"""Malé HTML pomocníky pro readonly panely v Django adminu.

``copy_row`` vykreslí hodnotu s tlačítkem "Kopírovat do schránky"; obsluhu
kliknutí má ``static/js/admin_copy_code.js`` (žádný inline JS kvůli CSP).
"""

from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

_ROW_STYLE = "display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:8px;"
_LABEL_STYLE = "min-width:170px; color:#64748b; font-size:12px; text-transform:uppercase; letter-spacing:0.06em;"
_VALUE_STYLE = (
    "font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px;"
    " padding:4px 8px; border:1px solid #cbd5e1; border-radius:6px; background:#f8fafc; color:#0f172a;"
)


def copy_row(label, value, *, copy_label="Kopírovat do schránky"):
    """Řádek ``label: value`` s tlačítkem pro zkopírování hodnoty."""
    if not value:
        return format_html(
            '<div style="{}"><span style="{}">{}</span><span>-</span></div>',
            _ROW_STYLE,
            _LABEL_STYLE,
            label,
        )
    return format_html(
        '<div style="{}">'
        '<span style="{}">{}</span>'
        '<code style="{}">{}</code>'
        '<button type="button" class="button bmx-copy-btn" data-copy-value="{}">{}</button>'
        "</div>",
        _ROW_STYLE,
        _LABEL_STYLE,
        label,
        _VALUE_STYLE,
        value,
        value,
        copy_label,
    )


def panel(rows, note=""):
    """Sloupec řádků (např. z ``copy_row``) s volitelnou poznámkou pod nimi."""
    body = format_html_join("", "{}", ((row,) for row in rows if row))
    if note:
        return format_html(
            '<div>{}<p style="margin-top:6px; color:#64748b; font-size:12px;">{}</p></div>',
            body,
            mark_safe(note),
        )
    return format_html("<div>{}</div>", body)
