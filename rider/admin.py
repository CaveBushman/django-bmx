from django.contrib import admin
from .models import ForeignRider, Rider
from django.utils.html import format_html
from import_export.admin import ExportMixin
from import_export import resources

# Register your models here.

from import_export import resources
from .models import Rider

class RiderResource(resources.ModelResource):
    class Meta:
        model = Rider
        fields = (
            'id',
            'uci_id',
            'first_name',
            'middle_name',
            'last_name',
            'date_of_birth',
            'gender',
            'nationality',
            'email',
            'phone',
            'street',
            'city',
            'zip',
            'club__team_name',           # FK na klub (název týmu)
            'club__region',              # FK – kraj
            'plate',
            'plate_champ_20',
            'plate_champ_24',
            'plate_color_20',
            'ranking_20',
            'ranking_24',
            'points_20',
            'points_24',
            'is_20',
            'is_24',
            'is_elite',
            'have_girl_bonus',
            'is_in_talent_team',
            'is_in_representation',
            'is_qualify_to_cn_20',
            'is_qualify_to_cn_24',
            'class_20',
            'class_24',
            'class_beginner',
            'transponder_20',
            'transponder_24',
            'emergency_contact',
            'emergency_phone',
            'have_valid_insurance',
            'valid_licence',
            'fix_valid_licence',
            'is_active',
            'is_approwe',
            'created',
            'updated',
        )
        export_order = fields  # zachová stejné pořadí při exportu

class RiderAdmin(ExportMixin, admin.ModelAdmin):

    resource_class = RiderResource

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
