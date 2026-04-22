import logging

from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone


logger = logging.getLogger("bmx.context")


def navbar_context(request):
    from accounts.models import AvatarChangeRequest
    from eshop.models import Order
    from rider.models import Rider
    from todo.models import CommissionTask

    if request.user.is_authenticated:
        try:
            account = request.user
            is_task_user = getattr(request.user, "is_commission", False)
            navbar_data = {"user_credit": getattr(account, "credit", 0)}

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
            return {"user_credit": 0}
        except DatabaseError as error:
            logger.warning(
                "Navbar context fallback due to database error for user_id=%s: %s",
                getattr(request.user, "id", None),
                error,
            )
            return {"user_credit": getattr(request.user, "credit", 0)}
    return {}


def seo_context(request):
    return {
        "seo_canonical_url": f"{settings.YOUR_DOMAIN.rstrip('/')}{request.path}",
        "seo_default_description": (
            "Oficialni web Czech BMX. Aktuality, kalendar zavodu, vysledky, "
            "propozice a informace pro jezdce, kluby a rozhodci."
        ),
        "seo_site_name": "Czech BMX",
    }
