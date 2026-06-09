"""
Centrální email service pro HTML e-maily.

Použití:
    from bmx.email import send_html_email
    send_html_email(
        subject="Předmět",
        template="emails/activation.html",
        context={"user": user, "activation_url": url},
        to=["user@example.com"],
    )
"""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

_SITE_URL = getattr(settings, "YOUR_DOMAIN", "https://czechbmx.cz").rstrip("/")


def send_html_email(subject: str, template: str, context: dict, to: list[str], *, fail_silently: bool = False) -> bool:
    """
    Odešle HTML e-mail s plain-text fallbackem.
    Vrátí True při úspěchu, False při chybě (pokud fail_silently=True).
    """
    ctx = {"site_url": _SITE_URL, **context}

    html_body = render_to_string(template, ctx)
    text_body = strip_tags(html_body).strip()
    # Zredukujeme přebytečné prázdné řádky z strip_tags
    text_body = "\n".join(line for line in text_body.splitlines() if line.strip())

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=None,  # použije DEFAULT_FROM_EMAIL
        to=to,
    )
    msg.attach_alternative(html_body, "text/html")

    try:
        msg.send()
        return True
    except Exception:
        logger.exception("Odeslání e-mailu selhalo: subject=%r to=%r", subject, to)
        if not fail_silently:
            raise
        return False
