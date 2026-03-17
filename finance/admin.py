from django.contrib import admin
from .models import EventInvoice, EventInvoiceOverride, SubscriptionInvoice


@admin.register(EventInvoice)
class EventInvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "event", "club", "issue_date", "due_date", "total_price", "email_sent_to", "email_sent_at")
    search_fields = ("number", "event__name", "club__team_name", "club__ico")
    list_filter = ("issue_date", "event")


@admin.register(EventInvoiceOverride)
class EventInvoiceOverrideAdmin(admin.ModelAdmin):
    list_display = ("event", "club", "updated")
    search_fields = ("event__name", "club__team_name")


@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "invoice_type", "customer_name", "issue_date", "total_price")
    search_fields = ("number", "customer_name", "customer_email", "description")
    list_filter = ("invoice_type", "issue_date")
