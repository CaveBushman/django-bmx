from django.contrib import admin
from .models import Club, McrClubTeam, McrClubTeamMember

class ClubAdmin(admin.ModelAdmin):
    list_display = ('id', 'team_name', 'contact_email', 'billing_email')
    list_display_links = ('id', 'team_name')
    search_fields = ('team_name', 'contact_email', 'ico')

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
