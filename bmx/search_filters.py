import unicodedata
from rest_framework.filters import SearchFilter


def normalize_query(text: str) -> str:
    """Strip diacritics and lowercase, same logic as normalize_search_text."""
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


class NormalizedSearchFilter(SearchFilter):
    """SearchFilter that strips diacritics from the query before matching."""

    def get_search_terms(self, request):
        terms = super().get_search_terms(request)
        if not terms:
            return terms
        return [normalize_query(t) for t in terms]
