from rest_framework import serializers
from .models import News

_SUPPORTED_LANGS = frozenset(("en", "de", "sk", "es", "it", "fr", "pl", "hu"))
_TRANSLATED_FIELDS = (
    [f"title_{l}" for l in _SUPPORTED_LANGS] +
    [f"perex_{l}" for l in _SUPPORTED_LANGS] +
    [f"content_{l}" for l in _SUPPORTED_LANGS]
)


class NewsSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    perex = serializers.SerializerMethodField()
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

    def get_title(self, obj) -> str:
        lang = self._lang()
        if lang != "cs":
            translated = getattr(obj, f"title_{lang}", "") or ""
            if translated.strip():
                return translated
        return obj.title

    def get_perex(self, obj) -> str | None:
        lang = self._lang()
        if lang != "cs":
            translated = getattr(obj, f"perex_{lang}", "") or ""
            if translated.strip():
                return translated
        return obj.perex

    def get_content(self, obj) -> str | None:
        lang = self._lang()
        if lang != "cs":
            translated = getattr(obj, f"content_{lang}", "") or ""
            if translated.strip():
                return translated
        return obj.content
