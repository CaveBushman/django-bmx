from django.contrib import admin
from .models import News

# Register your models here.

class NewsAdmin (admin.ModelAdmin):

    list_display = ('title', 'on_homepage', 'published')
    list_display_links = ('title',)
    list_editable = ('on_homepage', 'published')
    search_fields = ('title', 'perex', 'content')
    list_filter = ('on_homepage', 'published','created_date')

    

admin.site.register(News, NewsAdmin)