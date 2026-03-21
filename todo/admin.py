from django.contrib import admin
from django.db.models import Q

from accounts.models import Account
from .models import CommissionTask


@admin.register(CommissionTask)
class CommissionTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "event",
        "assignee",
        "created_by",
        "status",
        "priority",
        "due_date",
        "updated",
    )
    list_filter = ("status", "priority", "due_date", "event")
    search_fields = (
        "title",
        "description",
        "event__name",
        "assignee__first_name",
        "assignee__last_name",
        "created_by__first_name",
        "created_by__last_name",
    )
    list_select_related = ("event", "assignee", "created_by")
    readonly_fields = ("completed_at", "created", "updated")
    fieldsets = (
        (
            "Ukol",
            {
                "fields": (
                    "title",
                    "description",
                    "event",
                    ("status", "priority"),
                    ("assignee", "created_by"),
                    ("due_date", "completed_at"),
                )
            },
        ),
        ("Historie", {"fields": ("created", "updated")}),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in {"assignee", "created_by"}:
            kwargs["queryset"] = Account.objects.filter(is_active=True).filter(
                Q(is_commission=True)
                | Q(is_staff=True)
                | Q(is_admin=True)
                | Q(is_superuser=True)
            ).order_by("last_name", "first_name")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
