from django_ical.views import ICalFeed
from .models import Event
from django.urls import reverse

class EventFeed(ICalFeed):
    """
    Generuje živý iCal (ics) feed se všemi závody pro externí kalendáře.
    """
    product_id = '-//BMX Website//Events//CZ'
    timezone = 'Europe/Prague'
    file_name = "bmx-events.ics"

    def items(self):
        # Vybere všechny nezrušené závody seřazené od nejnovějších
        return Event.objects.filter(canceled=False).select_related(
            'organizer', 'structured_proposition'
        ).order_by('-date')

    def item_title(self, item):
        return item.name

    def item_description(self, item):
        # Model nemá description, sestavíme ho z typu a pořadatele
        parts = []
        if item.type_for_ranking:
            parts.append(item.type_for_ranking)
        return "\n".join(parts)

    def item_start_datetime(self, item):
        return item.date

    def item_location(self, item):
        # Adresa se zobrazí v kalendáři jako místo konání a aplikace
        # (Google/Apple/Outlook) z ní umí přímo nabídnout navigaci.
        proposition = getattr(item, "structured_proposition", None)
        if proposition and proposition.is_published and proposition.venue_address:
            return proposition.venue_address

        organizer = item.organizer
        if not organizer:
            return ""

        address_parts = []
        if organizer.street:
            address_parts.append(organizer.street)
        if organizer.city:
            city = organizer.city
            if organizer.zip_code:
                city = f"{organizer.zip_code} {city}"
            address_parts.append(city)

        if address_parts:
            return ", ".join(address_parts)

        return str(organizer)

    def item_geolocation(self, item):
        # GPS souřadnice areálu pořadatele (pole 'lon' v DB obsahuje
        # zeměpisnou šířku, 'lng' délku - viz club/serializers.py).
        organizer = item.organizer
        if organizer and organizer.lon and organizer.lng:
            return (organizer.lon, organizer.lng)
        return None

    def item_link(self, item):
        return reverse('event:event-detail', args=[item.pk])
