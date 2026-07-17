"""Django admin pro jezdce, transpondéry, předplatná a promo kódy."""

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export.admin import ExportMixin
from import_export import resources
from urllib.parse import urlencode
from bmx.admin_search import DiacriticsInsensitiveSearchAdminMixin
from accounts.models import AccountRiderLink
from event.models import EntryForeign
from ranking.ranking import get_ranking_recount_status
from .models import (
    ForeignRider,
    MobileAppCharge,
    MobileAppSubscription,
    PromoCode,
    PromoCodeUsage,
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
            'mcr_wild_card_20',
            'mcr_wild_card_24',
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


class RiderDataIssueFilter(admin.SimpleListFilter):
    title = "datová kvalita"
    parameter_name = "data_issue"

    def lookups(self, request, model_admin):
        return (
            ("missing_club", "Chybí klub"),
            ("missing_photo", "Chybí fotka"),
            ("missing_transponder", "Chybí transpondér"),
            ("ranking_mismatch", "Body bez aktivní disciplíny"),
            ("inactive_unapproved", "Aktivní, ale neschválený"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "missing_club":
            return queryset.filter(club__isnull=True)
        if value == "missing_photo":
            return queryset.filter(Q(photo__isnull=True) | Q(photo="") | Q(photo="images/riders/uni.jpeg"))
        if value == "missing_transponder":
            return queryset.filter(
                (Q(is_20=True) & (Q(transponder_20__isnull=True) | Q(transponder_20="")))
                | (Q(is_24=True) & (Q(transponder_24__isnull=True) | Q(transponder_24="")))
            )
        if value == "ranking_mismatch":
            return queryset.filter(Q(is_20=False, points_20__gt=0) | Q(is_24=False, points_24__gt=0))
        if value == "inactive_unapproved":
            return queryset.filter(is_active=True, is_approved=False)
        return queryset


class RiderAdmin(PlateAwareSearchAdminMixin, DiacriticsInsensitiveSearchAdminMixin, ExportMixin, admin.ModelAdmin):

    resource_class = RiderResource
    change_list_template = "admin/rider/rider/change_list.html"

    def thumbnail(self, object):
        photo_url = object.photo_url
        if photo_url:
            return format_html(
                '<img src="{}" width="30" height="30" style="border-radius: 999px; object-fit: cover;" alt="{}" />',
                photo_url,
                object.initials,
            )
        return format_html(
            '<span style="display:inline-flex; width:30px; height:30px; align-items:center; justify-content:center; border-radius:999px; background:#e2e8f0; color:#334155; font-size:11px; font-weight:700;">{}</span>',
            object.initials or "?",
        )

    thumbnail.short_description = 'Foto'

    list_display = ('thumbnail','last_name','first_name', 'uci_id', 'club', 'plate_value','transponder_20', 'transponder_24','is_20', 'is_24', 'is_elite','data_quality_badges','is_active','is_approved')
    list_display_links = ('last_name',)
    ordering = ('last_name','first_name',)
    list_editable = ('is_20', 'is_24','is_elite','is_active','is_approved')
    search_fields = ('last_name', 'first_name', 'uci_id', 'transponder_20', 'transponder_24', 'plate_text')
    list_filter = ('is_20', 'is_24','gender',  'is_approved', 'is_active', 'valid_licence', 'club', RiderDataIssueFilter)
    readonly_fields = ('public_links', 'transponder_change_overview', 'data_quality_summary',)
    list_select_related = ('club',)
    inlines = (RiderAccountLinkInline,)
    actions = ('approve_selected_riders', 'activate_selected_riders')

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
                ('mcr_wild_card_20', 'mcr_wild_card_24'),
                ('is_in_talent_team', 'is_in_representation'),
            ),
        }),
        ('Kontrola dat', {
            'fields': ('data_quality_summary',),
        }),
        ('Rychlé odkazy', {
            'fields': ('public_links',),
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

    def _collect_data_issues(self, obj):
        issues = []
        if obj.club_id is None:
            issues.append(("Chybí klub", "#dc2626"))
        photo_name = getattr(obj.photo, "name", "") if obj.photo else ""
        if not photo_name or photo_name == "images/riders/uni.jpeg":
            issues.append(("Chybí fotka", "#d97706"))
        if obj.is_20 and not obj.transponder_20:
            issues.append(('Chybí čip 20"', "#7c3aed"))
        if obj.is_24 and not obj.transponder_24:
            issues.append(('Chybí čip 24"', "#2563eb"))
        if not obj.is_20 and obj.points_20 > 0:
            issues.append(('Body 20" bez aktivní disciplíny', "#b91c1c"))
        if not obj.is_24 and obj.points_24 > 0:
            issues.append(('Body 24" bez aktivní disciplíny', "#1d4ed8"))
        if obj.is_active and not obj.is_approved:
            issues.append(("Aktivní, ale neschválený", "#b45309"))
        return issues

    @admin.display(description='Kontrola dat')
    def data_quality_badges(self, obj):
        issues = self._collect_data_issues(obj)
        if not issues:
            return mark_safe(
                '<span style="display:inline-flex; padding:4px 8px; border-radius:999px; background:#dcfce7; color:#166534; font-weight:600;">OK</span>'
            )
        chips = [
            format_html(
                '<span style="display:inline-flex; padding:4px 8px; margin:0 6px 6px 0; border-radius:999px; background:{}15; color:{}; font-weight:600;">{}</span>',
                color,
                color,
                label,
            )
            for label, color in issues[:3]
        ]
        if len(issues) > 3:
            chips.append(
                format_html(
                    '<span style="display:inline-flex; padding:4px 8px; margin:0 6px 6px 0; border-radius:999px; background:#e2e8f0; color:#334155; font-weight:600;">+{} další</span>',
                    len(issues) - 3,
                )
            )
        return format_html("{}", mark_safe("".join(str(chip) for chip in chips)))

    @admin.display(description='Souhrn kvality dat')
    def data_quality_summary(self, obj):
        if not obj.pk:
            return "Kontrola bude dostupná po prvním uložení jezdce."
        issues = self._collect_data_issues(obj)
        if not issues:
            return format_html(
                '<div style="padding:12px 14px; border:1px solid #bbf7d0; border-radius:16px; background:#f0fdf4; color:#166534; font-weight:600;">{}</div>',
                "Profil je konzistentní. Nenašel jsem žádný zjevný datový problém.",
            )
        rows = "".join(f'<li style="margin:0 0 8px 0;">{label}</li>' for label, _ in issues)
        return format_html(
            '<div style="padding:14px 16px; border:1px solid #fed7aa; border-radius:16px; background:#fff7ed;">'
            '<p style="margin:0 0 10px 0; font-weight:700; color:#9a3412;">Vyžaduje kontrolu</p>'
            '<ul style="margin:0; padding-left:18px; color:#7c2d12;">{}</ul>'
            '</div>',
            mark_safe(rows),
        )

    @admin.display(description='Rychlé odkazy')
    def public_links(self, obj):
        if not obj.pk:
            return "Odkazy budou dostupné po prvním uložení jezdce."

        link_markup = [
            format_html(
                '<span style="display:inline-flex; padding:6px 10px; border:1px solid #cbd5e1; border-radius:999px;"><a href="{}" target="_blank" rel="noopener">Veřejný profil</a></span>',
                reverse("rider:detail", args=[obj.uci_id]),
            ),
            format_html(
                '<span style="display:inline-flex; padding:6px 10px; border:1px solid #cbd5e1; border-radius:999px;"><a href="{}" target="_blank" rel="noopener">Prémiové statistiky</a></span>',
                reverse("rider:premium-stats", args=[obj.uci_id]),
            ),
        ]
        if obj.class_20:
            link_markup.append(
                format_html(
                    '<span style="display:inline-flex; padding:6px 10px; border:1px solid #cbd5e1; border-radius:999px;"><a href="{}" target="_blank" rel="noopener">Ranking 20"</a></span>',
                    "{}?{}".format(reverse("ranking:ranking"), urlencode({"category": obj.class_20})),
                )
            )
        return format_html('<div style="display:flex; gap:12px; flex-wrap:wrap;">{}{}</div>', mark_safe("".join(link_markup[:2])), mark_safe("".join(link_markup[2:])))

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
        extra_context["ranking_recount_status"] = get_ranking_recount_status()
        return super().changelist_view(request, extra_context=extra_context)

    @admin.action(description="Schválit vybrané jezdce")
    def approve_selected_riders(self, request, queryset):
        updated = queryset.filter(is_approved=False).update(is_approved=True)
        self.message_user(request, f"Schváleno jezdců: {updated}.", level=messages.SUCCESS)

    @admin.action(description="Aktivovat vybrané jezdce")
    def activate_selected_riders(self, request, queryset):
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f"Aktivováno jezdců: {updated}.", level=messages.SUCCESS)

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

class MobileAppSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "season", "status", "expires_at", "monthly_price", "auto_renew")
    list_filter = ("status", "auto_renew", "season")
    search_fields = ("user__email", "user__last_name", "user__first_name")
    list_select_related = ("user", "season")


class MobileAppChargeAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "reason", "period_start", "period_end", "payment_valid")
    list_filter = ("reason", "payment_valid", "season")
    search_fields = ("user__email", "user__last_name", "user__first_name")
    list_select_related = ("user", "season", "subscription")


class PromoCodeUsageInline(admin.TabularInline):
    model = PromoCodeUsage
    extra = 0
    readonly_fields = ("user", "product", "discount_applied", "used_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "product", "discount_type", "discount_value", "used_count", "max_uses", "is_active", "valid_until", "created_by")
    list_filter = ("product", "discount_type", "is_active")
    search_fields = ("code", "description")
    readonly_fields = ("used_count", "created", "updated")
    inlines = [PromoCodeUsageInline]


admin.site.register(Rider, RiderAdmin)
admin.site.register(ForeignRider, ForeignRiderAdmin)
admin.site.register(RiderStatsSubscription, RiderStatsSubscriptionAdmin)
admin.site.register(RiderStatsCharge, RiderStatsChargeAdmin)
admin.site.register(TrainerClubSubscription, TrainerClubSubscriptionAdmin)
admin.site.register(TrainerClubCharge, TrainerClubChargeAdmin)
admin.site.register(RiderTransponderChange, RiderTransponderChangeAdmin)
admin.site.register(MobileAppSubscription, MobileAppSubscriptionAdmin)
admin.site.register(MobileAppCharge, MobileAppChargeAdmin)
admin.site.register(PromoCode, PromoCodeAdmin)
