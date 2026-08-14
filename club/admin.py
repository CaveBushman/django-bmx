import logging

from django.conf import settings
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from bmx.admin_widgets import copy_row, panel

from .models import Club, McrClubTeam, McrClubTeamMember

audit_logger = logging.getLogger("audit")


class ClubAdmin(admin.ModelAdmin):
    list_display = ('id', 'team_name', 'contact_email', 'billing_email', 'event_control_enabled')
    list_display_links = ('id', 'team_name')
    search_fields = ('team_name', 'contact_email', 'ico', 'event_control_id')
    list_filter = ('event_control_enabled',)
    readonly_fields = ('event_control_panel',)

    class Media:
        js = ("js/admin_copy_code.js",)

    def get_urls(self):
        custom = [
            path(
                "<int:club_id>/event-control-credentials/",
                self.admin_site.admin_view(self.event_control_credentials_view),
                name="club_club_event_control_credentials",
            ),
        ]
        return custom + super().get_urls()

    @staticmethod
    def _server_url():
        base_url = (getattr(settings, "YOUR_DOMAIN", "") or "").rstrip("/")
        return f"{base_url}/api/v1/event-control/"

    def event_control_credentials_view(self, request, club_id):
        """Vygeneruje/zneplatní přístupové údaje organizace pro BMX Event Control."""
        club = self.get_object(request, club_id)
        if club is None:
            return self._get_obj_does_not_exist_redirect(request, self.model._meta, str(club_id))

        generated_password = None
        if request.method == "POST":
            action = request.POST.get("action", "")
            if action == "generate":
                generated_password = club.generate_event_control_credentials()
                audit_logger.info(
                    "club_event_control_credentials_generated admin_user_id=%s club_id=%s",
                    request.user.id,
                    club.id,
                )
                messages.success(
                    request,
                    _("Přístupové údaje byly vygenerovány. Heslo se zobrazí jen teď — ulož si ho."),
                )
            elif action == "revoke":
                club.revoke_event_control_credentials()
                audit_logger.info(
                    "club_event_control_credentials_revoked admin_user_id=%s club_id=%s",
                    request.user.id,
                    club.id,
                )
                messages.success(request, _("Přístup pro BMX Event Control byl zneplatněn."))
                return redirect(reverse("admin:club_club_change", args=[club.pk]))

        return TemplateResponse(
            request,
            "admin/club/club/event_control_credentials.html",
            {
                "club": club,
                "server_url": self._server_url(),
                "generated_password": generated_password,
                "events": club.club.order_by("-date")[:10],
                "opts": self.model._meta,
                **self.admin_site.each_context(request),
            },
        )

    @admin.display(description=_("BMX Event Control"))
    def event_control_panel(self, obj):
        """Připojovací údaje organizace (server + username) a správa hesla."""
        if not obj.pk:
            return _("Přístupové údaje lze vygenerovat po prvním uložení klubu.")

        rows = [
            copy_row(_("Server"), self._server_url()),
            copy_row(_("Username"), obj.event_control_username or ""),
        ]

        if obj.event_control_password:
            state = _("Heslo nastaveno %(when)s.") % {
                "when": obj.event_control_password_updated.strftime("%d.%m.%Y %H:%M")
                if obj.event_control_password_updated
                else "-",
            }
        else:
            state = _("Heslo není nastaveno — vygeneruj přístupové údaje.")

        if obj.event_control_last_access:
            state += " " + (_("Poslední přístup: %(when)s.") % {
                "when": obj.event_control_last_access.strftime("%d.%m.%Y %H:%M"),
            })
        if not obj.event_control_enabled:
            state += " " + str(_("Přístup je vypnutý."))

        url = reverse("admin:club_club_event_control_credentials", args=[obj.pk])
        note = '<a href="{}" class="button">{}</a><br><span>{}</span>'.format(
            url,
            _("Vygenerovat / změnit heslo"),
            state,
        )
        return panel(rows, note=note)


admin.site.register(Club, ClubAdmin)


class McrClubTeamMemberInline(admin.TabularInline):
    model = McrClubTeamMember
    extra = 0
    autocomplete_fields = ("rider",)


@admin.register(McrClubTeam)
class McrClubTeamAdmin(admin.ModelAdmin):
    list_display = ("year", "club", "name", "manager_name", "updated")
    list_filter = ("year", "club")
    search_fields = ("name", "manager_name", "club__team_name")
    autocomplete_fields = ("club", "created_by")
    inlines = (McrClubTeamMemberInline,)
