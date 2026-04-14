import logging

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.admin.views.main import ChangeList
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from bmx.admin_search import DiacriticsInsensitiveSearchAdminMixin
from .models import Account, AccountActivationAuditLog, AccountRiderLink, AvatarChangeRequest, PendingActivationAccount, PendingAvatarChangeRequest
from .views import send_activation_email


logger = logging.getLogger(__name__)


class AccountRiderLinkInline(admin.TabularInline):
    model = AccountRiderLink
    extra = 1
    autocomplete_fields = ("rider",)
    verbose_name = "Navázaný jezdec"
    verbose_name_plural = "Navázaní jezdci"

# Register your models here.

class AccountAdmin(DiacriticsInsensitiveSearchAdminMixin, UserAdmin):
    list_display = ('email', 'last_name', 'first_name', 'club', 'is_club_manager', 'is_trainer', 'last_login', 'date_joined', 'is_active')
    list_display_links = ('email',)
    readonly_fields = ('last_login', 'date_joined', 'activation_status_badge', 'activation_admin_actions', 'activation_audit_preview')
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
        ('Aktivace účtu', {
            'fields': ('activation_status_badge', 'activation_admin_actions', 'activation_audit_preview'),
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:account_id>/resend-activation/",
                self.admin_site.admin_view(self.resend_activation_email_view),
                name="accounts_account_resend_activation",
            ),
        ]
        return custom_urls + urls

    @admin.action(description="Znovu poslat aktivační e-mail")
    def resend_activation_email_action(self, request, queryset):
        sent = 0
        for user in queryset.filter(is_active=False):
            send_activation_email(
                request,
                user,
                action=AccountActivationAuditLog.Action.RESENT,
                source="admin_bulk",
            )
            sent += 1
        self.message_user(
            request,
            _("Aktivační e-mail znovu odeslán pro %(count)s účtů.") % {"count": sent},
            level=messages.SUCCESS,
        )

    def resend_activation_email_view(self, request, account_id):
        user = Account.objects.filter(pk=account_id).first()
        if not user:
            self.message_user(request, _("Uživatel nebyl nalezen."), level=messages.ERROR)
            return HttpResponseRedirect(reverse("admin:accounts_account_changelist"))
        if user.is_active:
            self.message_user(request, _("Účet je už aktivní."), level=messages.WARNING)
            return HttpResponseRedirect(reverse("admin:accounts_account_change", args=[user.pk]))

        send_activation_email(
            request,
            user,
            action=AccountActivationAuditLog.Action.RESENT,
            source="admin_detail",
        )
        self.message_user(
            request,
            _("Aktivační e-mail byl znovu odeslán na %(email)s.") % {"email": user.email},
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:accounts_account_change", args=[user.pk]))

    @admin.display(description="Stav aktivace")
    def activation_status_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="display:inline-flex;padding:6px 10px;border-radius:999px;background:#dcfce7;color:#166534;font-weight:600;">{}</span>',
                _("Aktivní"),
            )
        return format_html(
            '<span style="display:inline-flex;padding:6px 10px;border-radius:999px;background:#fef3c7;color:#92400e;font-weight:600;">{}</span>',
            _("Čeká na aktivaci"),
        )

    @admin.display(description="Akce aktivace")
    def activation_admin_actions(self, obj):
        if not obj or obj.is_active:
            return "-"
        url = reverse("admin:accounts_account_resend_activation", args=[obj.pk])
        return format_html('<a class="button" href="{}">{}</a>', url, _("Znovu poslat aktivaci"))

    @admin.display(description="Poslední aktivační audit")
    def activation_audit_preview(self, obj):
        if not obj:
            return "-"
        logs = obj.activation_audit_logs.select_related("actor").order_by("-created_at")[:5]
        if not logs:
            return _("Žádné záznamy")
        items = []
        for log in logs:
            actor = log.actor.email if log.actor else _("systém")
            items.append(f"{log.created_at:%d.%m.%Y %H:%M} • {log.get_action_display()} • {actor}")
        return format_html("<br>".join(items))


admin.site.register(Account, AccountAdmin)
admin.site.register(AccountRiderLink)


class PendingActivationAccountChangeList(ChangeList):
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.filter(is_active=False)


@admin.register(PendingActivationAccount)
class PendingActivationAccountAdmin(AccountAdmin):
    actions = ("resend_activation_email_action",)

    def get_changelist(self, request, **kwargs):
        return PendingActivationAccountChangeList

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_active=False)


@admin.register(AccountActivationAuditLog)
class AccountActivationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "email_snapshot", "account", "actor", "source")
    list_filter = ("action", "source", "created_at")
    search_fields = ("email_snapshot", "account__email", "actor__email", "note")
    readonly_fields = ("created_at",)


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
                    if obj.status in {
                        AvatarChangeRequest.STATUS_APPROVED,
                        AvatarChangeRequest.STATUS_REJECTED,
                        AvatarChangeRequest.STATUS_EXPIRED,
                    }:
                        previous.review(obj.status, request.user, note=obj.review_note)
                        return
                except ValidationError as exc:
                    request._avatar_review_failed = True
                    request._avatar_review_error = "; ".join(exc.messages)
                    obj.status = previous.status
                    obj.review_note = previous.review_note
                    return
                except Exception as exc:
                    logger.exception(
                        "Avatar approval failed for request pk=%s by user=%s",
                        previous.pk,
                        getattr(request.user, "pk", None),
                    )
                    request._avatar_review_failed = True
                    request._avatar_review_error = (
                        f"Žádost se nepodařilo zpracovat: {exc}"
                        if str(exc)
                        else "Žádost se nepodařilo zpracovat. Zkontroluj zdrojový obrázek a zkus to znovu."
                    )
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

    def _process_bulk_action(self, request, queryset, processor, *, success_label):
        updated = 0
        failed = 0

        for avatar_request in queryset.filter(status=AvatarChangeRequest.STATUS_PENDING):
            try:
                processor(avatar_request)
                updated += 1
            except ValidationError as exc:
                failed += 1
                self.message_user(
                    request,
                    f"{avatar_request.target_label}: {'; '.join(exc.messages)}",
                    level=messages.ERROR,
                )
            except Exception as exc:
                failed += 1
                logger.exception(
                    "Avatar bulk action failed for request pk=%s by user=%s",
                    avatar_request.pk,
                    getattr(request.user, "pk", None),
                )
                self.message_user(
                    request,
                    (
                        f"{avatar_request.target_label}: žádost se nepodařilo zpracovat"
                        + (f" ({exc})" if str(exc) else ".")
                    ),
                    level=messages.ERROR,
                )

        self.message_user(request, f"{success_label}: {updated} žádostí.")
        if failed:
            self.message_user(request, f"Selhalo: {failed} žádostí.", level=messages.WARNING)

    @admin.action(description="Schválit vybrané žádosti")
    def approve_selected(self, request, queryset):
        self._process_bulk_action(
            request,
            queryset,
            lambda avatar_request: avatar_request.approve(request.user),
            success_label="Schváleno",
        )

    @admin.action(description="Zamítnout vybrané žádosti")
    def reject_selected(self, request, queryset):
        self._process_bulk_action(
            request,
            queryset,
            lambda avatar_request: avatar_request.reject(request.user),
            success_label="Zamítnuto",
        )


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
