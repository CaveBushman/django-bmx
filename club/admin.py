from django.contrib import admin
from .models import Club
# Register your models here.

class ClubAdmin(admin.ModelAdmin):

    list_display = ('id', 'team_name', 'contact_email', 'billing_email')
    list_display_links = ('id', 'team_name')

admin.site.register(Club, ClubAdmin)
