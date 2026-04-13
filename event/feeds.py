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
        return Event.objects.filter(canceled=False).order_by('-date')

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
        return str(item.organizer)

    def item_link(self, item):
        return reverse('event:event-detail', args=[item.pk])
