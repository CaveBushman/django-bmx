from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.admin.views.main import ChangeList
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from .models import Account, AccountRiderLink, AvatarChangeRequest, PendingAvatarChangeRequest


class AccountRiderLinkInline(admin.TabularInline):
    model = AccountRiderLink
    extra = 1
    autocomplete_fields = ("rider",)
    verbose_name = "Navázaný jezdec"
    verbose_name_plural = "Navázaní jezdci"

# Register your models here.

class AccountAdmin(UserAdmin):
    list_display = ('email', 'last_name', 'first_name', 'club', 'is_club_manager', 'is_trainer', 'last_login', 'date_joined', 'is_active')
    list_display_links = ('email',)
    readonly_fields = ('last_login', 'date_joined')
    ordering = ('-date_joined',)
    search_fields = ('email', 'first_name', 'last_name', 'username', 'club__team_name')
    list_filter = ('is_active', 'is_staff', 'is_admin', 'is_club_manager', 'is_trainer', 'club')

    filter_horizontal = ('trainer_clubs',)
    inlines = (AccountRiderLinkInline,)
    fieldsets = (
        ('Přihlášení', {
            'fields': ('email', 'username', 'password'),
        }),
        ('Osobní údaje', {
            'fields': ('first_name', 'last_name', 'phone_number', 'photo'),
        }),
        ('Klubové přiřazení', {
            'fields': ('club', 'is_club_manager', 'is_trainer', 'trainer_clubs'),
        }),
        ('Oprávnění', {
            'fields': (
                'is_active',
                'is_staff',
                'is_admin',
                'is_superuser',
                'is_rider',
                'is_commission',
                'is_commissar',
            ),
        }),
        ('Finance a historie', {
            'fields': ('credit', 'last_login', 'date_joined'),
        }),
    )


admin.site.register(Account, AccountAdmin)
admin.site.register(AccountRiderLink)


@admin.register(AvatarChangeRequest)
class AvatarChangeRequestAdmin(admin.ModelAdmin):
    list_display = (
        "target_label",
        "uploaded_by",
        "status",
        "created",
        "reviewed_by",
        "reviewed_at",
        "image_preview",
    )
    list_filter = ("status", "created", "reviewed_at")
    search_fields = (
        "uploaded_by__email",
        "uploaded_by__first_name",
        "uploaded_by__last_name",
        "target_account__email",
        "target_account__first_name",
        "target_account__last_name",
        "target_rider__first_name",
        "target_rider__last_name",
        "target_rider__uci_id",
    )
    readonly_fields = ("created", "reviewed_at", "reviewed_by", "image_preview")
    actions = ("approve_selected", "reject_selected")

    fieldsets = (
        ("Žádost", {
            "fields": ("uploaded_by", "target_account", "target_rider", "status", "image", "image_preview"),
        }),
        ("Revize", {
            "fields": ("review_note", "reviewed_by", "reviewed_at", "created"),
        }),
    )

    def save_model(self, request, obj, form, change):
        if change:
            previous = AvatarChangeRequest.objects.get(pk=obj.pk)
            status_changed = "status" in form.changed_data and previous.status != obj.status
            if status_changed and previous.status == AvatarChangeRequest.STATUS_PENDING:
                previous.review_note = obj.review_note
                try:
                    if obj.status == AvatarChangeRequest.STATUS_APPROVED:
                        previous.approve(request.user, note=obj.review_note)
                        return
                    if obj.status == AvatarChangeRequest.STATUS_REJECTED:
                        previous.reject(request.user, note=obj.review_note)
                        return
                    if obj.status == AvatarChangeRequest.STATUS_EXPIRED:
                        previous.expire(note=obj.review_note)
                        return
                except ValidationError as exc:
                    request._avatar_review_failed = True
                    request._avatar_review_error = "; ".join(exc.messages)
                    obj.status = previous.status
                    obj.review_note = previous.review_note
                    return
                except Exception:
                    request._avatar_review_failed = True
                    request._avatar_review_error = "Žádost se nepodařilo zpracovat. Zkontroluj zdrojový obrázek a zkus to znovu."
                    obj.status = previous.status
                    obj.review_note = previous.review_note
                    return

        super().save_model(request, obj, form, change)

    def response_change(self, request, obj):
        if getattr(request, "_avatar_review_failed", False):
            self.message_user(
                request,
                getattr(request, "_avatar_review_error", "Žádost se nepodařilo zpracovat."),
                level=messages.ERROR,
            )
            return HttpResponseRedirect(request.path)
        return super().response_change(request, obj)

    @admin.display(description="Náhled")
    def image_preview(self, obj):
        if not obj.image_url:
            return "-"
        return format_html('<img src="{}" style="max-height: 120px; border-radius: 12px;" />', obj.image_url)

    @admin.action(description="Schválit vybrané žádosti")
    def approve_selected(self, request, queryset):
        updated = 0
        for avatar_request in queryset.filter(status=AvatarChangeRequest.STATUS_PENDING):
            avatar_request.approve(request.user)
            updated += 1
        self.message_user(request, f"Schváleno: {updated} žádostí.")

    @admin.action(description="Zamítnout vybrané žádosti")
    def reject_selected(self, request, queryset):
        updated = 0
        for avatar_request in queryset.filter(status=AvatarChangeRequest.STATUS_PENDING):
            avatar_request.reject(request.user)
            updated += 1
        self.message_user(request, f"Zamítnuto: {updated} žádostí.")


class PendingAvatarChangeRequestChangeList(ChangeList):
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.filter(status=AvatarChangeRequest.STATUS_PENDING)


@admin.register(PendingAvatarChangeRequest)
class PendingAvatarChangeRequestAdmin(AvatarChangeRequestAdmin):
    actions = ("approve_selected", "reject_selected")

    def get_changelist(self, request, **kwargs):
        return PendingAvatarChangeRequestChangeList

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=AvatarChangeRequest.STATUS_PENDING)
