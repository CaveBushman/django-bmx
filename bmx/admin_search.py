from bmx.text_normalization import normalize_search_text


class DiacriticsInsensitiveSearchAdminMixin:
    normalized_search_field = "search_text_normalized"

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        normalized_term = normalize_search_text(search_term)
        if not normalized_term:
            return queryset, use_distinct

        normalized_queryset = self.model.objects.filter(
            **{f"{self.normalized_search_field}__icontains": normalized_term}
        )
        queryset |= normalized_queryset
        return queryset, use_distinct
