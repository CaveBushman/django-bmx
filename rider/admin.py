from django.contrib import admin
from .models import ForeignRider, Rider
from django.utils.html import format_html

# Register your models here.

class RiderAdmin(admin.ModelAdmin):

    def thumbnail(self, object):
        return format_html('<img src="{}" width="30" style="border-radius: 50px;" />'.format(object.photo.url))

    thumbnail.short_description = 'Foto'

    list_display = ('thumbnail','last_name','first_name', 'uci_id', 'club', 'plate','transponder_20', 'transponder_24','is_20', 'is_24', 'is_elite','is_active','is_approwe')
    list_display_links = ('last_name',)
    ordering = ('last_name','first_name',)
    list_editable = ('is_20', 'is_24','is_elite','is_active','is_approwe')
    search_fields = ('last_name', 'uci_id', 'transponder_20', 'transponder_24', 'plate',)
    list_filter = ('is_20', 'is_24','gender',  'is_approwe', 'is_active', 'valid_licence', 'club',)

class ForeignRiderAdmin(admin.ModelAdmin):

    list_display = ('last_name', 'first_name', 'uci_id', 'plate','transponder_20', 'transponder_24','state','club','is_20', 'is_24', 'is_elite',)
    list_display_links = ('last_name',)
    ordering = ('last_name',)
    search_fields = ('last_name', 'first_name', 'uci_id', 'transponder_20', 'transponder_24', 'plate')
    list_filter = ('state',)

admin.site.register(Rider, RiderAdmin)
admin.site.register(ForeignRider, ForeignRiderAdmin)
