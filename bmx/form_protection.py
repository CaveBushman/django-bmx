import datetime

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _


DEFAULT_FORM_PROTECTION = {
    "signup": {
        "min_fill_seconds": 3,
        "rate_limit_window_seconds": 60 * 15,
        "rate_limit_max_attempts": 5,
        "captcha_after_attempts": 2,
    },
    "signin": {
        "min_fill_seconds": 1,
        "rate_limit_window_seconds": 60 * 15,
        "rate_limit_max_attempts": 10,
        "captcha_after_attempts": 3,
    },
    "password_reset": {
        "min_fill_seconds": 1,
        "rate_limit_window_seconds": 60 * 15,
        "rate_limit_max_attempts": 5,
        "captcha_after_attempts": 2,
    },
    "activation_resend": {
        "min_fill_seconds": 1,
        "rate_limit_window_seconds": 60 * 15,
        "rate_limit_max_attempts": 5,
        "captcha_after_attempts": 2,
    },
    "rider_request": {
        "min_fill_seconds": 3,
        "rate_limit_window_seconds": 60 * 15,
        "rate_limit_max_attempts": 5,
        "captcha_after_attempts": 2,
    },
}

FORM_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 2
HUMAN_CHALLENGE_MAX_AGE_SECONDS = 60 * 30
FORM_TOKEN_SALT_PREFIX = "forms.token"
HUMAN_CHALLENGE_SALT_PREFIX = "forms.captcha"
HONEYPOT_FIELD_NAME = "website"


def get_flow_settings(flow):
    config = DEFAULT_FORM_PROTECTION[flow].copy()
    config.update(getattr(settings, "FORM_PROTECTION", {}).get(flow, {}))
    return config


def build_flow_token(flow, created_at=None):
    created_at = created_at or timezone.now()
    return signing.dumps(
        {"ts": created_at.timestamp()},
        salt=f"{FORM_TOKEN_SALT_PREFIX}.{flow}",
    )


def _attempts_key(flow, request):
    return f"form-protection:{flow}:{request.META.get('REMOTE_ADDR', 'unknown')}"


def increment_flow_attempts(flow, request):
    config = get_flow_settings(flow)
    cache_key = _attempts_key(flow, request)
    attempts = cache.get(cache_key, 0) + 1
    cache.set(cache_key, attempts, config["rate_limit_window_seconds"])
    return attempts


def clear_flow_attempts(flow, request):
    cache.delete(_attempts_key(flow, request))


def get_flow_attempts(flow, request):
    return cache.get(_attempts_key(flow, request), 0)


def flow_requires_human_check(flow, request):
    return get_flow_attempts(flow, request) >= get_flow_settings(flow)["captcha_after_attempts"]


def build_human_challenge(flow):
    left = timezone.now().microsecond % 7 + 2
    right = timezone.now().second % 8 + 1
    token = signing.dumps(
        {"answer": left + right},
        salt=f"{HUMAN_CHALLENGE_SALT_PREFIX}.{flow}",
    )
    return {
        "human_check_question": f"{left} + {right}",
        "human_check_token": token,
    }


def build_security_context(flow, request):
    context = {
        "form_token": build_flow_token(flow),
        "honeypot_field_name": HONEYPOT_FIELD_NAME,
        "requires_human_check": flow_requires_human_check(flow, request),
    }
    if context["requires_human_check"]:
        context.update(build_human_challenge(flow))
    return context


def protect_public_flow(flow, request):
    config = get_flow_settings(flow)

    if get_flow_attempts(flow, request) >= config["rate_limit_max_attempts"]:
        return {
            "status": 429,
            "reason": "rate_limited",
            "message": _("Zkus to prosím znovu za několik minut."),
        }

    if request.POST.get(HONEYPOT_FIELD_NAME, "").strip():
        increment_flow_attempts(flow, request)
        return {
            "status": 400,
            "reason": "honeypot",
            "message": _("Formulář se nepodařilo ověřit. Zkus to prosím znovu."),
        }

    form_token = request.POST.get("form_token", "")
    try:
        token_payload = signing.loads(
            form_token,
            max_age=FORM_TOKEN_MAX_AGE_SECONDS,
            salt=f"{FORM_TOKEN_SALT_PREFIX}.{flow}",
        )
    except signing.BadSignature:
        increment_flow_attempts(flow, request)
        return {
            "status": 400,
            "reason": "invalid_token",
            "message": _("Platnost formuláře vypršela. Otevři stránku znovu."),
        }

    created_at = datetime.datetime.fromtimestamp(token_payload["ts"], tz=datetime.timezone.utc)
    if (timezone.now() - created_at).total_seconds() < config["min_fill_seconds"]:
        increment_flow_attempts(flow, request)
        return {
            "status": 400,
            "reason": "too_fast",
            "message": _("Počkej prosím chvíli před odesláním. Chceme se ujistit, že jsi člověk."),
        }

    if flow_requires_human_check(flow, request):
        challenge_token = request.POST.get("human_check_token", "")
        expected_answer = request.POST.get("human_check_answer", "").strip()
        try:
            payload = signing.loads(
                challenge_token,
                max_age=HUMAN_CHALLENGE_MAX_AGE_SECONDS,
                salt=f"{HUMAN_CHALLENGE_SALT_PREFIX}.{flow}",
            )
        except signing.BadSignature:
            payload = None

        if payload is None or expected_answer != str(payload["answer"]):
            increment_flow_attempts(flow, request)
            return {
                "status": 400,
                "reason": "human_check",
                "message": _("Ověření, že nejste robot, se nepodařilo."),
            }

    return None
