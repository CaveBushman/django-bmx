import logging
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.exceptions import ValidationError
from django.core.exceptions import MultipleObjectsReturned
from django.template.response import TemplateResponse
from django.urls import reverse
from django.urls import NoReverseMatch
from django.utils.html import format_html
from .models import Event, Result, EntryClasses, Entry, EntryForeign, EntryAuditLog, FinanceAuditLog, SeasonSettings, CreditTransaction, DebetTransaction, StripeFee, EventProposition, normalize_uci_id
from rider.models import ForeignRider
from django.utils.timezone import now
from datetime import timedelta
from django.contrib import messages

from event.services.checkout_refunds import apply_entry_checkout

audit_logger = logging.getLogger("audit")


def create_finance_audit_log(*, actor, action, source, target_model, obj, note=""):
    FinanceAuditLog.objects.create(
        actor=actor,
        action=action,
        source=source,
        target_model=target_model,
        target_object_id=obj.pk,
        target_user_id_snapshot=getattr(obj, "user_id", None),
        amount_snapshot=getattr(obj, "amount", 0) or 0,
        transaction_kind_snapshot=getattr(obj, "kind", "") or "",
        payment_complete_snapshot=getattr(obj, "payment_complete", None),
        payment_valid_snapshot=getattr(obj, "payment_valid", None),
        note=note or "",
    )

# Base Admin Class for common fields
class BaseAdmin(admin.ModelAdmin):
    search_fields = ()
    list_display_links = ()
    list_filter = ()
    list_editable = ()
    list_select_related = ()
    autocomplete_fields = ()


class ResultAdmin(BaseAdmin):
    list_display = ('event', 'rider','last_name',)
    list_display_links = ('event', 'rider',)
    search_fields = ('event__name', 'rider','last_name',)
    list_filter = ('event__name',)


class EventAdmin(BaseAdmin):
    list_display = (
        'id',
        'name',
        'date',
        'organizer',
        'type_for_ranking',
        'reg_open',
        'reg_open_from',
        'reg_open_to',
        'reg_cancel_to',
        'pcp',
        'pcp_assist',
        'start_commissar',
        'classes_and_fees_like',
        'xls_results',
    )
    list_display_links = ('name',)
    search_fields = ('name', 'organizer',)
    list_filter = ('type_for_ranking', 'reg_open', 'date')


class EntryClassesAdmin(BaseAdmin):
    fieldsets = (
        ('Název závodu', {
            "fields": ('event_name',),
        }),
        ('Kategorie příchozí', {
            "fields": (('beginners_1', 'beginners_2', 'beginners_3', 'beginners_4')),
        }),
        ('Kategorie muži', {
            "fields": (('boys_6', 'boys_7'), ('boys_8', 'boys_9'), ('boys_10', 'boys_11'),
                        ('boys_12', 'boys_13'), ('boys_14', 'boys_15'), ('boys_16', 'men_17_24'), ('men_25_29', 'men_30_34'),
                        ('men_35_over', 'men_junior'), ('men_u23', 'men_elite')),
        }),
        ('Kategorie ženy', {
            "fields": (('girls_6', 'girls_7'), ('girls_8', 'girls_9'), ('girls_10', 'girls_11'),
                        ('girls_12', 'girls_13'), ('girls_14', 'girls_15'), ('girls_16', 'women_17_24'), ('women_25_over', 'women_junior'), ('women_u23', 'women_elite')),
        }),
        ('Kategorie Cruiser', {
            'fields': (('cr_boys_12_and_under', 'cr_boys_13_14'), ('cr_boys_15_16', 'cr_men_17_24'),
                        ('cr_men_25_29', 'cr_men_30_34'), ('cr_men_35_39', 'cr_men_40_44'), ('cr_men_45_49', 'cr_men_50_and_over'),
                        ('cr_girls_12_and_under', 'cr_girls_13_16'), ('cr_women_17_29', 'cr_women_30_39'), ('cr_women_40_and_over',)),
        }),
        ('Startovné Příchozí', {
            "fields": ('beginners_1_fee', 'beginners_2_fee', 'beginners_3_fee', 'beginners_4_fee'),
        }),
        ('Startovné muži', {
            "fields": (('boys_6_fee', 'boys_7_fee', 'boys_8_fee', 'boys_9_fee'), ('boys_10_fee', 'boys_11_fee', 'boys_12_fee', 'boys_13_fee'), ('boys_14_fee', 'boys_15_fee', 'boys_16_fee', 'men_17_24_fee'), ('men_25_29_fee', 'men_30_34_fee',
                        'men_35_over_fee', 'men_junior_fee'), ('men_u23_fee', 'men_elite_fee')),
        }),
        ('Startovné ženy', {
            'fields': (('girls_6_fee', 'girls_7_fee', 'girls_8_fee', 'girls_9_fee'), ('girls_10_fee', 'girls_11_fee', 'girls_12_fee', 'girls_13_fee'), ('girls_14_fee', 'girls_15_fee', 'girls_16_fee', 'women_17_24_fee'), ('women_25_over_fee', 'women_junior_fee', 'women_u23_fee', 'women_elite_fee'),),
        }),
        ('Startovné Cruiser', {
            'fields': (('cr_boys_12_and_under_fee', 'cr_boys_13_14_fee', 'cr_boys_15_16_fee', 'cr_men_17_24_fee'),
                        ('cr_men_25_29_fee', 'cr_men_30_34_fee', 'cr_men_35_39_fee', 'cr_men_40_44_fee'), ('cr_men_45_49_fee', 'cr_men_50_and_over_fee'),
                        ('cr_girls_12_and_under_fee', 'cr_girls_13_16_fee', 'cr_women_17_29_fee', 'cr_women_30_39_fee'), ('cr_women_40_and_over_fee',)),
        }),
    )


class EntryAdmin(BaseAdmin):
    list_display = ('rider', 'event', 'transaction_date', 'payment_complete', 'user', 'checkout', 'checkout_refund_link')
    list_display_links = ('rider',)
    search_fields = ('rider__last_name', 'event__name', 'user__last_name',)
    list_filter = ('payment_complete', 'event',)
    autocomplete_fields = ('rider', 'event', 'user')
    list_select_related = ('rider', 'event', 'user')
    actions = ("mark_checkout_with_refund", "unmark_checkout_and_remove_refund")
    action_confirmation_template = "admin/event/entry/checkout_action_confirmation.html"

    def get_readonly_fields(self, request, obj=None):
        return ("checkout",)

    def save_model(self, request, obj, form, change):
        previous_checkout = None
        if change and obj.pk:
            previous_checkout = Entry.objects.filter(pk=obj.pk).values_list("checkout", flat=True).first()

        super().save_model(request, obj, form, change)

        if previous_checkout is not None and previous_checkout != obj.checkout:
            audit_logger.info(
                "entry_checkout_changed_by_admin admin_user_id=%s entry_id=%s user_id=%s event_id=%s old_checkout=%s new_checkout=%s",
                request.user.id,
                obj.pk,
                obj.user_id,
                obj.event_id,
                previous_checkout,
                obj.checkout,
            )

    def _render_checkout_action_confirmation(self, request, queryset, *, checkout, action_name, title, note):
        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "entries": queryset,
            "action_name": action_name,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "checkout_target": checkout,
            "note": note,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, self.action_confirmation_template, context)

    def _apply_checkout_action(self, request, queryset, *, checkout, note):
        updated = 0
        skipped = 0
        for entry in queryset.select_related("user", "event", "rider"):
            try:
                if apply_entry_checkout(
                    entry,
                    checkout=checkout,
                    actor=request.user,
                    source="admin_action",
                    note=note,
                ):
                    updated += 1
            except ValidationError:
                skipped += 1
        return updated, skipped

    @admin.action(description=_("Zapnout checkout a vrátit startovné"))
    def mark_checkout_with_refund(self, request, queryset):
        note = "Bulk admin action: mark checkout with refund"
        if request.POST.get("apply") != "yes":
            return self._render_checkout_action_confirmation(
                request,
                queryset,
                checkout=True,
                action_name="mark_checkout_with_refund",
                title=_("Potvrzení vrácení startovného"),
                note=note,
            )
        updated, skipped = self._apply_checkout_action(request, queryset, checkout=True, note=note)
        self.message_user(
            request,
            _("Checkout byl zapnut u %(count)s registrací.") % {"count": updated},
            level=messages.SUCCESS,
        )
        if skipped:
            self.message_user(
                request,
                _("%(count)s registrací bylo přeskočeno kvůli nevalidnímu stavu.") % {"count": skipped},
                level=messages.WARNING,
            )

    @admin.action(description=_("Vypnout checkout a smazat vratku startovného"))
    def unmark_checkout_and_remove_refund(self, request, queryset):
        note = "Bulk admin action: unmark checkout and remove refund"
        if request.POST.get("apply") != "yes":
            return self._render_checkout_action_confirmation(
                request,
                queryset,
                checkout=False,
                action_name="unmark_checkout_and_remove_refund",
                title=_("Potvrzení zrušení vratky startovného"),
                note=note,
            )
        updated, skipped = self._apply_checkout_action(request, queryset, checkout=False, note=note)
        self.message_user(
            request,
            _("Checkout byl vypnut u %(count)s registrací.") % {"count": updated},
            level=messages.SUCCESS,
        )
        if skipped:
            self.message_user(
                request,
                _("%(count)s registrací bylo přeskočeno kvůli nevalidnímu stavu.") % {"count": skipped},
                level=messages.WARNING,
            )

    @admin.display(description=_("Vratka kreditu"))
    def checkout_refund_link(self, obj):
        refund = obj.credit_transactions.filter(kind=CreditTransaction.Kind.CHECKOUT_REFUND).first()
        if not refund:
            return "-"
        try:
            url = reverse("admin:event_credittransaction_change", args=[refund.pk])
        except NoReverseMatch:
            return refund.payment_intent or "Vratka"
        return format_html('<a href="{}">{} Kč</a>', url, refund.amount)


class EntryForeignAdmin(BaseAdmin):
    list_display = (
        'last_name',
        'first_name',
        'uci_id',
        'event',
        'entry_category',
        'plate',
        'nationality',
        'payment_complete',
        'checkout',
        'transaction_date',
        'foreign_rider_link',
    )
    list_display_links = ('last_name', 'first_name')
    search_fields = (
        'last_name',
        'first_name',
        'uci_id',
        'event__name',
        'nationality',
        'plate',
        'customer_email',
        'transponder_20',
        'transponder_24',
    )
    list_filter = ('payment_complete', 'checkout', 'event', 'nationality', 'is_20', 'is_24', 'is_elite')
    list_editable = ('checkout',)
    autocomplete_fields = ('event',)
    list_select_related = ('event',)
    readonly_fields = ('transaction_id', 'transaction_date', 'date_of_payment', 'foreign_rider_link')
    ordering = ('-transaction_date', 'last_name', 'first_name')

    fieldsets = (
        ('Závod a platba', {
            'fields': (
                'event',
                'transaction_id',
                ('payment_complete', 'checkout'),
                ('transaction_date', 'date_of_payment'),
                'customer_email',
                'customer_name',
            ),
        }),
        ('Jezdec', {
            'fields': (
                ('first_name', 'last_name'),
                ('uci_id', 'date_of_birth'),
                ('gender', 'nationality'),
                ('plate', 'club'),
                'foreign_rider_link',
            ),
        }),
        ('Kategorie a transpondéry', {
            'fields': (
                ('is_20', 'is_24', 'is_elite'),
                ('class_20', 'class_24'),
                ('fee_20', 'fee_24'),
                ('transponder', 'transponder_20', 'transponder_24'),
            ),
        }),
    )

    @admin.display(description='Kategorie')
    def entry_category(self, obj):
        if obj.is_20:
            return obj.class_20 or '20"'
        if obj.is_24:
            return obj.class_24 or '24"'
        return '-'

    @admin.display(description='Zahraniční jezdec')
    def foreign_rider_link(self, obj):
        if not obj.uci_id:
            return "Bez UCI ID"
        normalized_uci_id = normalize_uci_id(obj.uci_id)
        if not normalized_uci_id:
            return "Nenalezen"
        try:
            foreign_rider = ForeignRider.objects.get(uci_id=int(normalized_uci_id))
        except (ForeignRider.DoesNotExist, ValidationError, ValueError):
            return "Nenalezen"
        except MultipleObjectsReturned:
            return "Duplicitní jezdec"

        try:
            url = reverse('admin:rider_foreignrider_change', args=[foreign_rider.pk])
        except NoReverseMatch:
            return "Detail nedostupný"
        return format_html('<a href="{}">Otevřít jezdce</a>', url)


class CreditTransactionAdmin(BaseAdmin):
    list_display = ('user', 'amount', 'kind', 'source_entry', 'payment_intent', 'payment_complete', 'transaction_date',)
    list_display_links = ('user',)
    search_fields = ('user__last_name', 'transaction_date', 'payment_intent', 'source_entry__event__name', 'source_entry__rider__last_name')
    list_filter = ('transaction_date', 'kind', 'payment_complete')

    def save_model(self, request, obj, form, change):
        note = ""
        action = FinanceAuditLog.Action.CREATED
        if change:
            action = FinanceAuditLog.Action.UPDATED
            note = ", ".join(form.changed_data) if getattr(form, "changed_data", None) else ""

        super().save_model(request, obj, form, change)
        create_finance_audit_log(
            actor=request.user,
            action=action,
            source="admin_credit_transaction",
            target_model="CreditTransaction",
            obj=obj,
            note=note,
        )

    def delete_model(self, request, obj):
        create_finance_audit_log(
            actor=request.user,
            action=FinanceAuditLog.Action.DELETED,
            source="admin_credit_transaction",
            target_model="CreditTransaction",
            obj=obj,
            note=obj.payment_intent or "",
        )
        super().delete_model(request, obj)


class EntryAuditLogAdmin(BaseAdmin):
    list_display = ("created_at", "action", "source", "entry_id_snapshot", "event_name_snapshot", "rider_name_snapshot", "old_checkout", "new_checkout", "actor")
    list_display_links = ("created_at",)
    search_fields = ("event_name_snapshot", "rider_name_snapshot", "note", "source")
    list_filter = ("action", "source", "new_checkout", "old_checkout")


class FinanceAuditLogAdmin(BaseAdmin):
    list_display = ("created_at", "action", "target_model", "target_object_id", "target_user_id_snapshot", "amount_snapshot", "transaction_kind_snapshot", "actor")
    list_display_links = ("created_at",)
    search_fields = ("target_model", "note", "transaction_kind_snapshot")
    list_filter = ("action", "target_model", "source")



class DebetTransactionAdmin(BaseAdmin):
    list_display = ('user', 'entry', 'amount', 'transaction_date',)
    list_display_links = ('user',)
    search_fields = ('user__last_name', 'transaction_date')
    list_filter = ('transaction_date',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "entry":
            two_months_ago = now().date() - timedelta(days=60)
            kwargs["queryset"] = Entry.objects.filter(created__gte=two_months_ago)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        note = ""
        action = FinanceAuditLog.Action.CREATED
        if change:
            action = FinanceAuditLog.Action.UPDATED
            note = ", ".join(form.changed_data) if getattr(form, "changed_data", None) else ""

        super().save_model(request, obj, form, change)
        create_finance_audit_log(
            actor=request.user,
            action=action,
            source="admin_debet_transaction",
            target_model="DebetTransaction",
            obj=obj,
            note=note,
        )

    def delete_model(self, request, obj):
        create_finance_audit_log(
            actor=request.user,
            action=FinanceAuditLog.Action.DELETED,
            source="admin_debet_transaction",
            target_model="DebetTransaction",
            obj=obj,
            note=str(obj.entry) if obj.entry else "",
        )
        super().delete_model(request, obj)

class StripeFeeAdmin(BaseAdmin):
    list_display = ('date', 'fee',)
    list_display_links = ('date',)


class EventPropositionAdmin(BaseAdmin):
    list_display = ('event', 'is_published', 'updated', 'updated_by')
    list_display_links = ('event',)
    search_fields = ('event__name', 'event__organizer__team_name', 'contact_name', 'contact_email')
    list_filter = ('is_published', 'event__organizer')
    autocomplete_fields = ('event', 'created_by', 'updated_by')
    list_select_related = ('event', 'event__organizer', 'updated_by')


# Registering models
admin.site.register(Event, EventAdmin)
admin.site.register(Result, ResultAdmin)
admin.site.register(EntryClasses, EntryClassesAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(EntryForeign, EntryForeignAdmin)
admin.site.register(SeasonSettings)
admin.site.register(CreditTransaction, CreditTransactionAdmin)
admin.site.register(FinanceAuditLog, FinanceAuditLogAdmin)
admin.site.register(DebetTransaction, DebetTransactionAdmin)
admin.site.register(StripeFee, StripeFeeAdmin)
admin.site.register(EventProposition, EventPropositionAdmin)
admin.site.register(EntryAuditLog, EntryAuditLogAdmin)
