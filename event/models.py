from django.db import models
from club.models import Club

from datetime import date


# Create your models here.

class Event(models.Model):
    """ class form event """

    EVENT_TYPE = (('Mistrovství ČR jednotlivců', 'Mistrovství ČR jednotlivců'),
                  ('Mistrovství ČR družstev', 'Mistrovství ČR družstev'), ('Český pohár', 'Český pohár'),
                  ('Česká liga', 'Česká liga'),
                  ('Moravská liga', 'Moravská liga'), ('Volný závod', 'Volný závod'),
                  ('Nebodovaný závod', 'Nebodovaný závod'), ('Mezinárodní závod', 'Mezinárodní závod'))
    
    RACE_SYSTEM = (('3 základní rozjíždky a KO system', '3 základní rozjíždky a KO system'), ('5 základních rozjíždek a KO system', '5 základních rozjíždek a KO system'))

    name = models.CharField(max_length=255, blank=False)
    date = models.DateField(null=True, blank=True)

    organizer = models.ForeignKey(Club, related_name='club', null=True, on_delete=models.SET_NULL)

    event_type = models.CharField(max_length=100, choices=EVENT_TYPE, default="Volný závod")
    classes_code = models.IntegerField(default = 3)
    is_uci_race = models.BooleanField(default=False)

    pcp = models.CharField(max_length=255, null=True, blank=True)
    pcp_assist = models.CharField(max_length=255, null=True, blank=True)
    director = models.CharField(max_length=255, null=True, blank=True)

    reg_open_from = models.DateField(default='2021-04-01')
    reg_open_to = models.DateField(default='2021-12-31')
    reg_open = models.BooleanField(default=True)

    system = models.CharField(choices=RACE_SYSTEM, default='3 základní rozjíždky a KO system', max_length=100, blank=True, null=True)
    prices = models.TextField(max_length=1000, default="", blank=True, null=True)
    timeschedule = models.TextField(max_length=1000, default="", blank=True, null=True)
    notes = models.TextField(max_length=1000, default="", blank=True, null=True)

    fee_boys_girls = models.IntegerField(default=300)  # CZK
    fee_men_women = models.IntegerField(default=300)  # CZK
    fee_junior = models.IntegerField(default=500)  # CZK
    fee_elite = models.IntegerField(default=800)  # CZK
    fee_cruiser = models.IntegerField(default=300)  # CZK

    bem_entries = models.FileField(upload_to='static/bem_entries', null = True, blank = True)
    bem_entries_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    bem_riders_list = models.FileField(upload_to='static/bem_riders', null = True, blank = True)
    bem_riders_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    full_results_path = models.FileField(upload_to='static/full_results', null = True, blank = True)
    full_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    results_path_to_file = models.FileField(upload_to='static/results', null=True, blank=True)
    results_uploaded = models.BooleanField(default=False)

    created = models.DateField(auto_now_add=True, null=True)

    canceled = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    def events_in_year(self, year):
        year = date.today().year
        events_in_year = Event.objects.filter(date__year=year).count()
        return events_in_year

    class Meta:
        verbose_name = "Závod"
        verbose_name_plural = 'Závody'
        ordering = ['-date',]


class Result(models.Model):
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    type = models.CharField(max_length=255, null=True, blank=True)
    organizer = models.CharField(max_length=100, null=True, blank=True)
    rider = models.IntegerField(default=0)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    club = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    place = models.IntegerField(default=0)
    points = models.IntegerField(default=0)
    is_20 = models.BooleanField(default=1)

    class Meta:
        verbose_name = "Výsledek"
        verbose_name_plural = "Výsledky"

    def __str__(self):
        return self.name + " " + str(self.last_name) + " " + self.first_name + " " + self.category


class Entry(models.Model):
    transaction_id = models.CharField(max_length=255, default="")
    event = models.IntegerField(default=0, null=True, blank=True)
    rider = models.IntegerField(default=0)
    is_20 = models.BooleanField(default=False)
    is_24 = models.BooleanField(default=False)
    class_20 = models.CharField(max_length=255, default="")
    class_24 = models.CharField(max_length=255, default="")
    fee_20 = models.IntegerField(null=True, blank=True, default=0)
    fee_24 = models.IntegerField(null=True, blank=True, default=0)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)
    payment_complete = models.BooleanField(default=False)
    logout = models.BooleanField(default=False)
    date_of_payment = models.DateField(auto_now_add=True, null=True)
