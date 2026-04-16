def normalize_uci_id(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())
