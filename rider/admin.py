from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export.admin import ExportMixin
from import_export import resources
from event.models import EntryForeign
from .models import ForeignRider, Rider, RiderStatsCharge, RiderStatsSubscription

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
            'is_approved',
            'created',
            'updated',
        )
        export_order = fields  # zachová stejné pořadí při exportu

class RiderAdmin(ExportMixin, admin.ModelAdmin):

    resource_class = RiderResource

    def thumbnail(self, object):
        return format_html(
            '<img src="{}" width="30" style="border-radius: 50px;" />',
            object.photo.url,
        )

    thumbnail.short_description = 'Foto'

    list_display = ('thumbnail','last_name','first_name', 'uci_id', 'club', 'plate','transponder_20', 'transponder_24','is_20', 'is_24', 'is_elite','is_active','is_approved')
    list_display_links = ('last_name',)
    ordering = ('last_name','first_name',)
    list_editable = ('is_20', 'is_24','is_elite','is_active','is_approved')
    search_fields = ('last_name', 'uci_id', 'transponder_20', 'transponder_24', 'plate',)
    list_filter = ('is_20', 'is_24','gender',  'is_approved', 'is_active', 'valid_licence', 'club',)

class ForeignRiderAdmin(admin.ModelAdmin):

    list_display = (
        'last_name',
        'first_name',
        'uci_id',
        'plate',
        'transponder_20',
        'transponder_24',
        'state',
        'club',
        'is_20',
        'is_24',
        'is_elite',
        'paid_entries_count',
        'last_paid_event',
    )
    list_display_links = ('last_name',)
    ordering = ('last_name', 'first_name')
    search_fields = ('last_name', 'first_name', 'uci_id', 'transponder_20', 'transponder_24', 'plate')
    list_filter = ('state', 'is_20', 'is_24', 'is_elite')
    readonly_fields = ('registration_overview',)
    fieldsets = (
        ('Identita', {
            'fields': (
                ('first_name', 'last_name'),
                ('uci_id', 'date_of_birth'),
                ('gender', 'state', 'nationality'),
                ('club', 'plate'),
            ),
        }),
        ('Kategorie a transpondéry', {
            'fields': (
                ('is_20', 'is_24', 'is_elite'),
                ('class_20', 'class_24'),
                ('transponder_20', 'transponder_24'),
            ),
        }),
        ('Registrace', {
            'fields': ('registration_overview',),
        }),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset

    @admin.display(description='Zaplacené registrace')
    def paid_entries_count(self, obj):
        return EntryForeign.objects.filter(uci_id=str(obj.uci_id), payment_complete=True).count()

    @admin.display(description='Poslední závod')
    def last_paid_event(self, obj):
        last_entry = (
            EntryForeign.objects.filter(uci_id=str(obj.uci_id), payment_complete=True)
            .select_related('event')
            .order_by('-transaction_date')
            .first()
        )
        if not last_entry or not last_entry.event:
            return '-'

        url = reverse('admin:event_entryforeign_change', args=[last_entry.pk])
        return format_html('<a href="{}">{}</a>', url, last_entry.event.name)

    @admin.display(description='Historie registrací')
    def registration_overview(self, obj):
        entries = (
            EntryForeign.objects.filter(uci_id=str(obj.uci_id))
            .select_related('event')
            .order_by('-transaction_date')[:8]
        )
        if not entries:
            return "Žádné registrace."

        rows = []
        for entry in entries:
            category = entry.class_20 if entry.is_20 else entry.class_24 if entry.is_24 else "-"
            status = "Zaplaceno" if entry.payment_complete else "Nezaplaceno"
            event_label = entry.event.name if entry.event else "Bez závodu"
            entry_url = reverse('admin:event_entryforeign_change', args=[entry.pk])
            rows.append(
                f'<tr>'
                f'<td style="padding:8px 12px;"><a href="{entry_url}">{event_label}</a></td>'
                f'<td style="padding:8px 12px;">{category}</td>'
                f'<td style="padding:8px 12px;">{status}</td>'
                f'<td style="padding:8px 12px;">{entry.transaction_date:%d.%m.%Y %H:%M}</td>'
                f'</tr>'
            )

        table = (
            '<table style="width:100%; border-collapse:collapse;">'
            '<thead>'
            '<tr>'
            '<th style="text-align:left; padding:8px 12px;">Závod</th>'
            '<th style="text-align:left; padding:8px 12px;">Kategorie</th>'
            '<th style="text-align:left; padding:8px 12px;">Stav</th>'
            '<th style="text-align:left; padding:8px 12px;">Datum</th>'
            '</tr>'
            '</thead>'
            '<tbody>'
            + ''.join(rows) +
            '</tbody>'
            '</table>'
        )
        return format_html("{}", mark_safe(table))

class RiderStatsSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "rider", "season", "status", "expires_at", "monthly_price", "auto_renew")
    list_filter = ("status", "auto_renew", "season")
    search_fields = ("user__email", "user__last_name", "rider__last_name", "rider__first_name", "rider__uci_id")
    list_select_related = ("user", "rider", "season")


class RiderStatsChargeAdmin(admin.ModelAdmin):
    list_display = ("user", "rider", "amount", "reason", "period_start", "period_end", "payment_valid")
    list_filter = ("reason", "payment_valid", "season")
    search_fields = ("user__email", "user__last_name", "rider__last_name", "rider__first_name", "rider__uci_id")
    list_select_related = ("user", "rider", "season", "subscription")

admin.site.register(Rider, RiderAdmin)
admin.site.register(ForeignRider, ForeignRiderAdmin)
admin.site.register(RiderStatsSubscription, RiderStatsSubscriptionAdmin)
admin.site.register(RiderStatsCharge, RiderStatsChargeAdmin)
