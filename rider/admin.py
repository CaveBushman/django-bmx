from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export.admin import ExportMixin
from import_export import resources
from bmx.admin_search import DiacriticsInsensitiveSearchAdminMixin
from accounts.models import AccountRiderLink
from event.models import EntryForeign
from .models import (
    ForeignRider,
    Rider,
    TrainerClubCharge,
    TrainerClubSubscription,
    RiderStatsCharge,
    RiderStatsSubscription,
    RiderTransponderChange,
)
from .plates import normalize_plate_value


class RiderAccountLinkInline(admin.TabularInline):
    model = AccountRiderLink
    extra = 1
    autocomplete_fields = ("account",)
    verbose_name = "Navázaný účet"
    verbose_name_plural = "Navázané účty"

class RiderResource(resources.ModelResource):
    def dehydrate_plate(self, obj):
        return obj.plate_display

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


class PlateAwareSearchAdminMixin:
    plate_search_field = "plate"

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        normalized_plate = normalize_plate_value(search_term)
        if normalized_plate.isdigit():
            queryset |= self.model.objects.filter(**{self.plate_search_field: int(normalized_plate)})

        return queryset, use_distinct


class RiderAdmin(PlateAwareSearchAdminMixin, DiacriticsInsensitiveSearchAdminMixin, ExportMixin, admin.ModelAdmin):

    resource_class = RiderResource
    change_list_template = "admin/rider/rider/change_list.html"

    def thumbnail(self, object):
        if not object.photo:
            return "-"
        return format_html(
            '<img src="{}" width="30" style="border-radius: 50px;" />',
            object.photo.url,
        )

    thumbnail.short_description = 'Foto'

    list_display = ('thumbnail','last_name','first_name', 'uci_id', 'club', 'plate_value','transponder_20', 'transponder_24','is_20', 'is_24', 'is_elite','is_active','is_approved')
    list_display_links = ('last_name',)
    ordering = ('last_name','first_name',)
    list_editable = ('is_20', 'is_24','is_elite','is_active','is_approved')
    search_fields = ('last_name', 'first_name', 'uci_id', 'transponder_20', 'transponder_24', 'plate_text')
    list_filter = ('is_20', 'is_24','gender',  'is_approved', 'is_active', 'valid_licence', 'club',)
    readonly_fields = ('transponder_change_overview',)
    inlines = (RiderAccountLinkInline,)

    @admin.display(description='Číslo')
    def plate_value(self, obj):
        return obj.plate_display

    fieldsets = (
        ('Identita', {
            'fields': (
                ('first_name', 'middle_name', 'last_name'),
                ('uci_id', 'date_of_birth'),
                ('gender', 'nationality'),
                ('club', 'plate', 'plate_text'),
            ),
        }),
        ('Kategorie a ranking', {
            'fields': (
                ('is_20', 'is_24', 'is_elite'),
                ('class_20', 'class_24', 'class_beginner'),
                ('points_20', 'points_24'),
                ('ranking_20', 'ranking_24'),
            ),
        }),
        ('Čipy a desky', {
            'fields': (
                ('transponder_20', 'transponder_24'),
                ('plate_champ_20', 'plate_champ_24', 'plate_color_20'),
                'transponder_change_overview',
            ),
        }),
        ('Status', {
            'fields': (
                ('is_active', 'is_approved'),
                ('valid_licence', 'fix_valid_licence'),
                ('have_valid_insurance',),
                ('is_qualify_to_cn_20', 'is_qualify_to_cn_24'),
                ('is_in_talent_team', 'is_in_representation'),
            ),
        }),
        ('Kontakt', {
            'fields': (
                ('email', 'phone'),
                ('street', 'city', 'zip'),
                ('emergency_contact', 'emergency_phone'),
                'photo',
            ),
        }),
    )

    def save_model(self, request, obj, form, change):
        previous = None
        if change and obj.pk:
            previous = Rider.objects.only('transponder_20', 'transponder_24').get(pk=obj.pk)

        super().save_model(request, obj, form, change)

        if not previous:
            return

        changes = (
            ('20', previous.transponder_20, obj.transponder_20),
            ('24', previous.transponder_24, obj.transponder_24),
        )
        for slot, old_transponder, new_transponder in changes:
            if old_transponder == new_transponder:
                continue

            RiderTransponderChange.objects.create(
                rider=obj,
                slot=slot,
                old_transponder=old_transponder or '',
                new_transponder=new_transponder or '',
                changed_by=request.user if request.user.is_authenticated else None,
            )

    @admin.display(description='Historie změn čipů')
    def transponder_change_overview(self, obj):
        if not obj.pk:
            return "Historie bude dostupná po prvním uložení jezdce."

        changes = (
            RiderTransponderChange.objects.filter(rider=obj)
            .select_related('changed_by')
            .order_by('-changed_at')[:12]
        )
        if not changes:
            return "Zatím bez zaznamenané změny čipu."

        rows = []
        for change in changes:
            changed_by = str(change.changed_by) if change.changed_by else '-'
            rows.append(
                f'<tr>'
                f'<td style="padding:8px 12px;">{change.get_slot_display()}</td>'
                f'<td style="padding:8px 12px;">{change.old_transponder or "-"}</td>'
                f'<td style="padding:8px 12px;">{change.new_transponder or "-"}</td>'
                f'<td style="padding:8px 12px;">{change.changed_at:%d.%m.%Y %H:%M}</td>'
                f'<td style="padding:8px 12px;">{change.battery_expected_until:%d.%m.%Y}</td>'
                f'<td style="padding:8px 12px;">{changed_by}</td>'
                f'</tr>'
            )

        table = (
            '<table style="width:100%; border-collapse:collapse;">'
            '<thead>'
            '<tr>'
            '<th style="text-align:left; padding:8px 12px;">Disciplína</th>'
            '<th style="text-align:left; padding:8px 12px;">Původní čip</th>'
            '<th style="text-align:left; padding:8px 12px;">Nový čip</th>'
            '<th style="text-align:left; padding:8px 12px;">Změněno</th>'
            '<th style="text-align:left; padding:8px 12px;">Předpoklad výměny</th>'
            '<th style="text-align:left; padding:8px 12px;">Uživatel</th>'
            '</tr>'
            '</thead>'
            '<tbody>'
            + ''.join(rows) +
            '</tbody>'
            '</table>'
        )
        return format_html("{}", mark_safe(table))

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "migrate-plates/",
                self.admin_site.admin_view(self.migrate_plate_text_view),
                name="rider_rider_migrate_plates",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["plate_migration_url"] = reverse("admin:rider_rider_migrate_plates")
        return super().changelist_view(request, extra_context=extra_context)

    def _copy_plate_values(self, model):
        records = list(
            model.objects.filter(plate__isnull=False, plate__gt=0).order_by("pk")
        )
        to_update = []
        copied = 0
        skipped = 0

        for record in records:
            current_value = (record.plate_text or "").strip()
            expected_value = str(record.plate)
            if current_value:
                skipped += 1
                continue
            record.plate_text = expected_value
            to_update.append(record)
            copied += 1

        if to_update:
            model.objects.bulk_update(to_update, ["plate_text"])

        return copied, skipped

    def migrate_plate_text_view(self, request):
        if not self.has_change_permission(request):
            return TemplateResponse(request, "admin/403.html", status=403)

        if request.method != "POST":
            context = {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": "Překlopení startovních čísel do textového pole",
                "plate_migration_url": reverse("admin:rider_rider_migrate_plates"),
            }
            return TemplateResponse(request, "admin/rider/rider/migrate_plates_confirm.html", context)

        with transaction.atomic():
            rider_copied, rider_skipped = self._copy_plate_values(Rider)
            foreign_copied, foreign_skipped = self._copy_plate_values(ForeignRider)

        self.message_user(
            request,
            (
                "Překlopení dokončeno. "
                f"Domácí jezdci: zkopírováno {rider_copied}, přeskočeno {rider_skipped}. "
                f"Zahraniční jezdci: zkopírováno {foreign_copied}, přeskočeno {foreign_skipped}."
            ),
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:rider_rider_changelist"))

class ForeignRiderAdmin(PlateAwareSearchAdminMixin, admin.ModelAdmin):

    list_display = (
        'last_name',
        'first_name',
        'uci_id',
        'plate_value',
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

    @admin.display(description='Číslo')
    def plate_value(self, obj):
        return obj.plate_display
    list_display_links = ('last_name',)
    ordering = ('last_name', 'first_name')
    search_fields = ('last_name', 'first_name', 'uci_id', 'transponder_20', 'transponder_24', 'plate_text')
    list_filter = ('state', 'is_20', 'is_24', 'is_elite')
    readonly_fields = ('registration_overview',)
    fieldsets = (
        ('Identita', {
            'fields': (
                ('first_name', 'last_name'),
                ('uci_id', 'date_of_birth'),
                ('gender', 'state', 'nationality'),
                ('club', 'plate', 'plate_text'),
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


class TrainerClubSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "club", "product", "season", "status", "expires_at", "monthly_price", "auto_renew")
    list_filter = ("product", "status", "auto_renew", "season")
    search_fields = ("user__email", "user__last_name", "club__team_name")
    list_select_related = ("user", "club", "season")


class TrainerClubChargeAdmin(admin.ModelAdmin):
    list_display = ("user", "club", "product", "amount", "reason", "period_start", "period_end", "payment_valid")
    list_filter = ("product", "reason", "payment_valid", "season")
    search_fields = ("user__email", "user__last_name", "club__team_name")
    list_select_related = ("user", "club", "season", "subscription")


class RiderTransponderChangeAdmin(admin.ModelAdmin):
    list_display = ('rider', 'slot', 'old_transponder', 'new_transponder', 'changed_at', 'battery_expected_until', 'changed_by')
    list_filter = ('slot', 'changed_at')
    search_fields = ('rider__last_name', 'rider__first_name', 'rider__uci_id', 'old_transponder', 'new_transponder')
    readonly_fields = ('rider', 'slot', 'old_transponder', 'new_transponder', 'changed_at', 'battery_expected_until', 'changed_by')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(Rider, RiderAdmin)
admin.site.register(ForeignRider, ForeignRiderAdmin)
admin.site.register(RiderStatsSubscription, RiderStatsSubscriptionAdmin)
admin.site.register(RiderStatsCharge, RiderStatsChargeAdmin)
admin.site.register(TrainerClubSubscription, TrainerClubSubscriptionAdmin)
admin.site.register(TrainerClubCharge, TrainerClubChargeAdmin)
admin.site.register(RiderTransponderChange, RiderTransponderChangeAdmin)
