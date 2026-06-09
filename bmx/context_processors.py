import logging

from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone


logger = logging.getLogger("bmx.context")


def navbar_context(request):
    from accounts.models import AvatarChangeRequest
    from eshop.models import EshopSettings, Order
    from rider.models import Rider
    from todo.models import CommissionTask

    eshop_public = EshopSettings.shop_is_public()

    if request.user.is_authenticated:
        try:
            account = request.user
            is_task_user = getattr(request.user, "is_commission", False)
            navbar_data = {
                "user_credit": getattr(account, "credit", 0),
                "navbar_eshop_visible": eshop_public or request.user.is_staff,
            }

            if request.user.is_superuser:
                pending_plate_count = Rider.objects.filter(is_approved=False).count()
                navbar_data.update(
                    {
                        "navbar_plate_pending_count": pending_plate_count,
                        "navbar_plate_pending": pending_plate_count > 0,
                    }
                )

            if request.user.is_staff:
                AvatarChangeRequest.expire_stale_requests()
                pending_avatar_count = AvatarChangeRequest.objects.filter(
                    status=AvatarChangeRequest.STATUS_PENDING
                ).count()
                navbar_data.update(
                    {
                        "navbar_avatar_pending_count": pending_avatar_count,
                        "navbar_avatar_pending": pending_avatar_count > 0,
                    }
                )

            if getattr(request.user, "is_admin", False):
                eshop_pending = Order.objects.exclude(
                    status__in=[Order.Status.DELIVERED, Order.Status.CANCELED]
                ).count()
                navbar_data["navbar_eshop_pending_count"] = eshop_pending

            if is_task_user:
                open_statuses = [
                    CommissionTask.STATUS_NEW,
                    CommissionTask.STATUS_IN_PROGRESS,
                    CommissionTask.STATUS_WAITING,
                ]
                my_open_tasks = CommissionTask.objects.filter(
                    assignee=request.user,
                    status__in=open_statuses,
                )
                overdue_exists = my_open_tasks.filter(
                    due_date__lt=timezone.localdate(),
                ).exists()
                navbar_data.update(
                    {
                        "navbar_task_count": my_open_tasks.count(),
                        "navbar_task_has_overdue": overdue_exists,
                    }
                )

            return navbar_data
        except AttributeError:
            return {"user_credit": 0, "navbar_eshop_visible": eshop_public}
        except DatabaseError as error:
            logger.warning(
                "Navbar context fallback due to database error for user_id=%s: %s",
                getattr(request.user, "id", None),
                error,
            )
            return {"user_credit": getattr(request.user, "credit", 0), "navbar_eshop_visible": eshop_public}
    return {"navbar_eshop_visible": eshop_public}


def seo_context(request):
    domain = settings.YOUR_DOMAIN.rstrip("/")
    canonical = f"{domain}{request.path}"

    # hreflang — pro každý aktivní jazyk sestavíme URL s prefixem /cs/, /en/ atd.
    # Výchozí (bez prefixu) je čeština — ta dostane x-default v šabloně.
    hreflang_urls = []
    for lang_code, _ in settings.LANGUAGES:
        if lang_code == settings.LANGUAGE_CODE:
            lang_url = canonical  # cs je výchozí, nemá prefix
        else:
            lang_url = f"{domain}/{lang_code}{request.path}"
        hreflang_urls.append((lang_code, lang_url))

    return {
        "seo_canonical_url": canonical,
        "seo_default_description": (
            "Oficiální web Czech BMX. Aktuality, kalendář závodů, výsledky, "
            "propozice a informace pro jezdce, kluby a rozhodčí."
        ),
        "seo_site_name": "Czech BMX",
        "seo_domain": domain,
        "seo_og_image_url": f"{domain}/static/images/homepage/bmx.png",
        "seo_hreflang_urls": hreflang_urls,
    }
