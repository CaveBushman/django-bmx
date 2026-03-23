from django import forms


class CKEditorWidget(forms.Textarea):
    """Compatibility widget for historical imports."""

    def __init__(self, attrs=None):
        default_attrs = {
            "rows": 12,
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)
