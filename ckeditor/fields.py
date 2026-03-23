from django.db import models

from .widgets import CKEditorWidget


class RichTextField(models.TextField):
    """Compatibility replacement for django-ckeditor RichTextField."""

    def formfield(self, **kwargs):
        kwargs.setdefault("widget", CKEditorWidget)
        return super().formfield(**kwargs)
