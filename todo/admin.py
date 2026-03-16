from django.contrib import admin
from django.db.models import Q

from accounts.models import Account
from .models import CommissionTask


@admin.register(CommissionTask)
class CommissionTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "assignee",
        "status",
        "priority",
        "due_date",
        "event",
        "updated",
    )
    list_filter = ("status", "priority", "due_date", "event")
    search_fields = (
        "title",
        "description",
        "assignee__first_name",
        "assignee__last_name",
        "created_by__first_name",
        "created_by__last_name",
        "event__name",
    )
    list_select_related = ("assignee", "created_by", "event")
    readonly_fields = ("completed_at", "created", "updated")
    fieldsets = (
        (
            "Ukol",
            {
                "fields": (
                    "title",
                    "description",
                    ("status", "priority"),
                    ("assignee", "created_by"),
                    ("due_date", "completed_at"),
                    "event",
                )
            },
        ),
        ("Historie", {"fields": ("created", "updated")}),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "assignee":
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
