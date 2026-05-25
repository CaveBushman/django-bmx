from django import forms
from django.contrib import admin
from django_ckeditor_5.widgets import CKEditor5Widget

from .models import News, Tag, Downloads, DocumentTag

# Register your models here.


class NewsAdminForm(forms.ModelForm):
    RICH_TEXT_FIELDS = ("prefix", "content")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.RICH_TEXT_FIELDS:
            self.fields[field_name].widget = CKEditor5Widget(config_name="news_content")

    class Meta:
        model = News
        fields = "__all__"


class DownloadsAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].widget = CKEditor5Widget(config_name="news_content")

    class Meta:
        model = Downloads
        fields = "__all__"

class NewsAdmin (admin.ModelAdmin):
    form = NewsAdminForm

    list_display = ('title', 'on_homepage', 'published', 'publish_in_app', "view_count")
    list_display_links = ('title',)
    list_editable = ('on_homepage', 'published', 'publish_in_app')
    search_fields = ('title', 'prefix', 'content')
    list_filter = ('on_homepage', 'published', 'publish_in_app', 'created_date')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_date','view_count')
    exclude = ('time_to_read',)
    
admin.site.register(News, NewsAdmin,)
admin.site.register(Tag)

class DownloadsAdmin(admin.ModelAdmin):
    form = DownloadsAdminForm
    list_display = ('title', 'published', 'downloads_count')
    list_display_links= ('title',)
    search_fields = ('title',)
    list_editable =('published',)

admin.site.register(Downloads, DownloadsAdmin)
admin.site.register(DocumentTag)
