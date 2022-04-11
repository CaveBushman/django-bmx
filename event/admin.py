from django.contrib import admin
from .models import Event, Result, EntryClasses

# Register your models here.

class ResultAdmin(admin.ModelAdmin):
    pass

class EventAdmin(admin.ModelAdmin):
    list_display = ('id','name', 'date', 'organizer', 'type_for_ranking', 'results_uploaded')
    list_editable = ('results_uploaded',)
    list_display_links = ('name',)


admin.site.register(Event, EventAdmin)
admin.site.register(Result)
admin.site.register(EntryClasses)
