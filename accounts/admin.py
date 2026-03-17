from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Account

# Register your models here.

class AccountAdmin(UserAdmin):
    list_display = ('email', 'last_name', 'first_name', 'club', 'is_club_manager', 'last_login', 'date_joined', 'is_active')
    list_display_links = ('email',)
    readonly_fields = ('last_login', 'date_joined')
    ordering = ('-date_joined',)
    search_fields = ('email', 'first_name', 'last_name', 'username', 'club__team_name')
    list_filter = ('is_active', 'is_staff', 'is_admin', 'is_club_manager', 'club')

    filter_horizontal = ()
    fieldsets = (
        ('Přihlášení', {
            'fields': ('email', 'username', 'password'),
        }),
        ('Osobní údaje', {
            'fields': ('first_name', 'last_name', 'phone_number', 'photo'),
        }),
        ('Klubové přiřazení', {
            'fields': ('club', 'is_club_manager'),
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
