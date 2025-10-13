from django.contrib import admin
from .models import News, Tag, Downloads, DocumentTag

# Register your models here.

class NewsAdmin (admin.ModelAdmin):

    list_display = ('title', 'on_homepage', 'published', "view_count")
    list_display_links = ('title',)
    list_editable = ('on_homepage', 'published')
    search_fields = ('title', 'perex', 'content')
    list_filter = ('on_homepage', 'published','created_date')
    readonly_fields = ('created_date','view_count')
    exclude = ('time_to_read',)
    
admin.site.register(News, NewsAdmin,)
admin.site.register(Tag)

class DownloadsAdmin(admin.ModelAdmin):
    list_display = ('title', 'published',)
    list_display_links= ('title',)
    search_fields = ('title',)
    list_editable =('published',)

admin.site.register(Downloads, DownloadsAdmin)
admin.site.register(DocumentTag)