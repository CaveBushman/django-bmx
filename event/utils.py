def normalize_uci_id(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def is_valid_uci_id(value):
    """UCI ID je přesně 11 ASCII číslic (``str.isdigit`` by pustil i např. „²“)."""
    return len(value) == 11 and value.isascii() and value.isdigit()
