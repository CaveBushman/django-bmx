import string


PLATE_MIN = 10
PLATE_MAX = 999
LETTER_PLATE_MAX = 99
PLATE_PREFIXES = list(string.ascii_uppercase)


def normalize_plate_value(value):
    return "" if value is None else str(value).strip().upper()


def legacy_plate_int(value):
    normalized = normalize_plate_value(value)
    return int(normalized) if normalized.isdigit() else 0


def resolve_plate_value(plate_text=None, plate=None):
    text_value = normalize_plate_value(plate_text)
    if text_value:
        return text_value

    if plate in (None, "", 0, "0"):
        return ""

    return normalize_plate_value(plate)


def display_plate(plate_text=None, plate=None, fallback="-"):
    resolved = resolve_plate_value(plate_text=plate_text, plate=plate)
    return resolved or fallback


def generate_available_plate_values(used_values):
    normalized_used = {
        normalize_plate_value(value)
        for value in used_values
        if normalize_plate_value(value)
    }

    numeric_free = [
        str(number)
        for number in range(PLATE_MIN, PLATE_MAX + 1)
        if str(number) not in normalized_used
    ]
    if numeric_free:
        return numeric_free

    for prefix in PLATE_PREFIXES:
        prefixed_free = [
            f"{prefix}{number}"
            for number in range(PLATE_MIN, LETTER_PLATE_MAX + 1)
            if f"{prefix}{number}" not in normalized_used
        ]
        if prefixed_free:
            return prefixed_free

    return []
