from django.conf import settings
from django.utils import timezone


def navbar_context(request):
    from accounts.models import AvatarChangeRequest
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
