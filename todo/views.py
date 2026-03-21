from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from accounts.models import Account

from .models import CommissionTask


def can_access_task_board(user):
    return user.is_authenticated and getattr(user, "is_commission", False)


@login_required(login_url="/login/")
@user_passes_test(can_access_task_board, login_url="/login/")
def task_list_view(request):
    selected_status = request.GET.get("status", "")
    selected_assignee = request.GET.get("assignee", "")
    selected_scope = request.GET.get("scope", "all")

    tasks = CommissionTask.objects.select_related("event", "assignee", "created_by")

    if selected_status:
        tasks = tasks.filter(status=selected_status)

    if selected_assignee:
        tasks = tasks.filter(assignee_id=selected_assignee)

    if selected_scope == "mine":
        tasks = tasks.filter(assignee=request.user)
    elif selected_scope == "open":
        tasks = tasks.exclude(
            status__in=[CommissionTask.STATUS_DONE, CommissionTask.STATUS_CANCELLED]
        )
    elif selected_scope == "overdue":
        tasks = tasks.exclude(
            status__in=[CommissionTask.STATUS_DONE, CommissionTask.STATUS_CANCELLED]
        ).filter(due_date__lt=timezone.localdate())

    all_tasks = CommissionTask.objects.select_related("event")
    open_statuses = [
        CommissionTask.STATUS_NEW,
        CommissionTask.STATUS_IN_PROGRESS,
        CommissionTask.STATUS_WAITING,
    ]
    commission_members = (
        Account.objects.filter(is_active=True)
        .filter(Q(is_commission=True))
        .order_by("last_name", "first_name")
    )

    context = {
        "tasks": tasks,
        "status_choices": CommissionTask.STATUS_CHOICES,
        "assignees": commission_members,
        "selected_status": selected_status,
        "selected_assignee": selected_assignee,
        "selected_scope": selected_scope,
        "open_count": all_tasks.filter(status__in=open_statuses).count(),
        "overdue_count": all_tasks.filter(status__in=open_statuses, due_date__lt=timezone.localdate()).count(),
        "done_count": all_tasks.filter(status=CommissionTask.STATUS_DONE).count(),
        "my_open_count": all_tasks.filter(status__in=open_statuses, assignee=request.user).count(),
        "today": timezone.localdate(),
    }
    return render(request, "todo/task_list.html", context)
