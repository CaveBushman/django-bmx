import unicodedata


def normalize_search_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    without_diacritics = "".join(
        char for char in text if not unicodedata.combining(char)
    )
    return " ".join(without_diacritics.lower().split())
