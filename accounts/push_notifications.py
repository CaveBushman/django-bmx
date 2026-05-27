"""
Push notifikace přes Firebase Cloud Messaging.

Nastavení v .env:
  FIREBASE_CREDENTIALS_JSON  — JSON obsah service account klíče (base64 nebo raw JSON string)
  FIREBASE_CREDENTIALS_PATH  — cesta k souboru serviceAccountKey.json (alternativa k JSON)

Service account klíč stáhni z Firebase Console:
  Project Settings → Service Accounts → Generate new private key
"""
import json
import logging
from typing import Iterable

logger = logging.getLogger(__name__)

_firebase_app = None


def _get_app():
    """Lazy-init Firebase Admin SDK. Vrátí None pokud není nakonfigurováno."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials
        from django.conf import settings

        cred_json = getattr(settings, "FIREBASE_CREDENTIALS_JSON", "")
        cred_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", "")

        if cred_json:
            import base64
            try:
                decoded = base64.b64decode(cred_json).decode("utf-8")
            except Exception:
                decoded = cred_json
            cred = credentials.Certificate(json.loads(decoded))
        elif cred_path:
            cred = credentials.Certificate(cred_path)
        else:
            logger.warning(
                "[FCM] Firebase není nakonfigurováno. "
                "Nastav FIREBASE_CREDENTIALS_JSON nebo FIREBASE_CREDENTIALS_PATH v .env."
            )
            return None

        try:
            _firebase_app = firebase_admin.get_app()
        except ValueError:
            _firebase_app = firebase_admin.initialize_app(cred)
        return _firebase_app

    except ImportError:
        logger.warning("[FCM] Balíček firebase-admin není nainstalován.")
        return None
    except Exception as exc:
        logger.error("[FCM] Inicializace Firebase selhala: %s", exc)
        return None


def _chunk(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def send_to_tokens(tokens: list[str], title: str, body: str, path: str = "") -> dict:
    """
    Odešle multicast notifikaci na seznam FCM tokenů.
    Vrátí {'success': int, 'failure': int, 'total': int}.
    Automaticky odstraní neplatné tokeny z DB.
    FCM multicast má limit 500 tokenů – funkce dávkuje automaticky.
    """
    if not tokens:
        return {"success": 0, "failure": 0, "total": 0}

    app = _get_app()
    if not app:
        return {"success": 0, "failure": 0, "total": len(tokens)}

    try:
        from firebase_admin import messaging
    except ImportError:
        logger.warning("[FCM] firebase_admin.messaging nelze importovat.")
        return {"success": 0, "failure": 0, "total": len(tokens)}

    data = {"path": path} if path else {}
    total_success = 0
    total_failure = 0
    stale_tokens = []

    for batch in _chunk(tokens, 500):
        try:
            message = messaging.MulticastMessage(
                notification=messaging.Notification(title=title, body=body),
                data=data,
                tokens=batch,
                android=messaging.AndroidConfig(priority="high"),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(sound="default"),
                    )
                ),
            )
            response = messaging.send_each_for_multicast(message, app=app)
            total_success += response.success_count
            total_failure += response.failure_count

            for idx, result in enumerate(response.responses):
                if not result.success and result.exception:
                    code = getattr(result.exception, "code", "")
                    if code in (
                        "registration-token-not-registered",
                        "invalid-registration-token",
                    ):
                        stale_tokens.append(batch[idx])

        except Exception as exc:
            logger.exception("[FCM] Chyba při odesílání dávky %d tokenů: %s", len(batch), exc)
            total_failure += len(batch)

    if stale_tokens:
        from accounts.models import FcmDevice
        deleted, _ = FcmDevice.objects.filter(token__in=stale_tokens).delete()
        logger.info("[FCM] Odstraněno %d neplatných tokenů.", deleted)

    logger.info(
        "[FCM] Odesláno: title=%r, path=%r, total=%d, success=%d, failure=%d",
        title, path, len(tokens), total_success, total_failure,
    )
    return {"success": total_success, "failure": total_failure, "total": len(tokens)}


def send_to_all_users(title: str, body: str, path: str = "") -> dict:
    """Odešle notifikaci všem registrovaným zařízením."""
    from accounts.models import FcmDevice
    tokens = list(FcmDevice.objects.values_list("token", flat=True))
    return send_to_tokens(tokens, title, body, path)


def send_to_users(user_ids: Iterable[int], title: str, body: str, path: str = "") -> dict:
    """Odešle notifikaci zařízením konkrétních uživatelů."""
    from accounts.models import FcmDevice
    tokens = list(
        FcmDevice.objects.filter(user_id__in=list(user_ids)).values_list("token", flat=True)
    )
    return send_to_tokens(tokens, title, body, path)
