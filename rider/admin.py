from django.contrib import admin
from .models import Rider
from django.utils.html import format_html

# Register your models here.

class RiderAdmin(admin.ModelAdmin):

    def thumbnail(self, object):
        return format_html('<img src="{}" width="40" style="border-radius: 50px;" />'.format(object.photo.url))

    thumbnail.short_description = 'Foto'

    list_display = ('thumbnail','last_name','first_name', 'uci_id', 'club', 'plate','transponder_20', 'transponder_24','is_20', 'is_24', 'is_active')
    list_display_links = ('last_name',)
    list_editable = ('is_20', 'is_24','is_active',)
    search_fields = ('last_name', 'uci_id', 'transponder_20', 'transponder_24', 'plate',)
    list_filter = ('is_20', 'is_24','gender',  'is_approwe', 'is_active', 'have_valid_licence', 'club')

admin.site.register(Rider, RiderAdmin)
