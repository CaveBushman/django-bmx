from django.contrib import admin

from .models import Sponsor


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = ("name", "valid_from", "valid_to", "sort_order", "is_published")
    list_filter = ("is_published", "valid_from")
    search_fields = ("name", "alt_text")
    ordering = ("sort_order", "name")

