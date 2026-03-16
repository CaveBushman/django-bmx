from django.utils import timezone


def navbar_context(request):
    from accounts.models import Account
    from todo.models import CommissionTask

    if request.user.is_authenticated:
        try:
            account = Account.objects.get(id=request.user.id)
            is_task_user = getattr(request.user, "is_commission", False)
            navbar_data = {"user_credit": account.credit}

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
        except Account.DoesNotExist:
            return {"user_credit": 0}
    return {}
