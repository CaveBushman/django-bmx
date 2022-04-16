from django.contrib import admin
from .models import Event, Result, EntryClasses

# Register your models here.

class ResultAdmin(admin.ModelAdmin):
    pass

class EventAdmin(admin.ModelAdmin):
    list_display = ('id','name', 'date', 'organizer', 'type_for_ranking', 'classes_and_fees_like', 'results_uploaded')
    list_display_links = ('name',)
    search_fields = ('name', 'organizer',)
    list_filter = ('type_for_ranking',)


admin.site.register(Event, EventAdmin)
admin.site.register(Result)
admin.site.register(EntryClasses)
