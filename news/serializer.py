from rest_framework import serializers
from .models import News

_SUPPORTED_LANGS = frozenset(("en", "de", "sk", "es", "it", "fr"))
_TRANSLATED_FIELDS = (
    [f"prefix_{l}" for l in _SUPPORTED_LANGS] +
    [f"content_{l}" for l in _SUPPORTED_LANGS]
)


class NewsSerializer(serializers.ModelSerializer):
    prefix = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()

    class Meta:
        model = News
        exclude = _TRANSLATED_FIELDS
        read_only_fields = ["id"]

    def _lang(self) -> str:
        request = self.context.get("request")
        if request:
            raw = request.META.get("HTTP_ACCEPT_LANGUAGE", "cs")
            lang = raw.split(",")[0].split("-")[0].strip().lower()[:2]
            return lang if lang in _SUPPORTED_LANGS else "cs"
        return "cs"

    def get_prefix(self, obj) -> str | None:
        lang = self._lang()
        if lang != "cs":
            translated = getattr(obj, f"prefix_{lang}", "") or ""
            if translated.strip():
                return translated
        return obj.prefix

    def get_content(self, obj) -> str | None:
        lang = self._lang()
        if lang != "cs":
            translated = getattr(obj, f"content_{lang}", "") or ""
            if translated.strip():
                return translated
        return obj.content
