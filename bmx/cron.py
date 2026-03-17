from rider.rider import refresh_valid_licences

def valid_licence_scheduled():
    """Spustí pravidelnou kontrolu platnosti licencí."""
    return refresh_valid_licences()
