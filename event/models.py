from faulthandler import is_enabled
from django.db import models
from sqlalchemy import true
from club.models import Club
from commissar.models import Commissar

from datetime import date

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from ckeditor.fields import RichTextField

# Create your models here.

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


class EntryClasses(models.Model):

    event_name = models.CharField(max_length=200)
    
    boys_6 = models.CharField(max_length=50, blank = true, null = true)
    boys_7 = models.CharField(max_length=50, blank = true, null = true)
    boys_8 = models.CharField(max_length=50, blank = true, null = true)
    boys_9 = models.CharField(max_length=50, blank = true, null = true)
    boys_10 = models.CharField(max_length=50, blank = true, null = true)
    boys_11 = models.CharField(max_length=50, blank = true, null = true)
    boys_12 = models.CharField(max_length=50, blank = true, null = true)
    boys_13 = models.CharField(max_length=50, blank = true, null = true)
    boys_14 = models.CharField(max_length=50, blank = true, null = true)
    boys_15 = models.CharField(max_length=50, blank = true, null = true)
    boys_16 = models.CharField(max_length=50, blank = true, null = true)
    men_17_24 = models.CharField(max_length=50, blank = true, null = true)
    men_25_29 = models.CharField(max_length=50, blank = true, null = true)
    men_30_34 = models.CharField(max_length=50, blank = true, null = true)
    men_35_over = models.CharField(max_length=50, blank = true, null = true)

    girls_7 = models.CharField(max_length=50, blank = true, null = true)
    girls_8 = models.CharField(max_length=50, blank = true, null = true)
    girls_9 = models.CharField(max_length=50, blank = true, null = true)
    girls_10 = models.CharField(max_length=50, blank = true, null = true)
    girls_11 = models.CharField(max_length=50, blank = true, null = true)
    girls_12 = models.CharField(max_length=50, blank = true, null = true)
    girls_13 = models.CharField(max_length=50, blank = true, null = true)
    girls_14 = models.CharField(max_length=50, blank = true, null = true)
    girls_15 = models.CharField(max_length=50, blank = true, null = true)
    girls_16 = models.CharField(max_length=50, blank = true, null = true)
    women_17_24 = models.CharField(max_length=50, blank = true, null = true)
    women_25_over = models.CharField(max_length=50, blank = true, null = true)

    men_junior = models.CharField(max_length=50, blank = true, null = true)
    men_u23 = models.CharField(max_length=50, blank = true, null = true)
    men_elite = models.CharField(max_length=50, blank = true, null = true)

    women_junior = models.CharField(max_length=50, blank = true, null = true)
    women_u23 = models.CharField(max_length=50, blank = true, null = true)
    women_elite = models.CharField(max_length=50, blank = true, null = true)

    cr_boys_12_and_under = models.CharField(max_length=50, blank = true, null = true)
    cr_boys_13_14 = models.CharField(max_length=50, blank = true, null = true)
    cr_boys_15_16 = models.CharField(max_length=50, blank = true, null = true)

    cr_men_17_24 = models.CharField(max_length=50, blank = true, null = true)
    cr_men_25_29 = models.CharField(max_length=50, blank = true, null = true)
    cr_men_30_34 = models.CharField(max_length=50, blank = true, null = true)
    cr_men_35_39 = models.CharField(max_length=50, blank = true, null = true)
    cr_men_40_49 = models.CharField(max_length=50, blank = true, null = true)
    cr_men_50_and_over = models.CharField(max_length=50, blank = true, null = true)

    cr_girls_12_and_under = models.CharField(max_length=50, blank = true, null = true)
    cr_girls_13_16 = models.CharField(max_length=50, blank = true, null = true)
    cr_women_17_29 = models.CharField(max_length=50, blank = true, null = true)
    cr_women_30_39 = models.CharField(max_length=50, blank = true, null = true)
    cr_women_40_and_over = models.CharField(max_length=50, blank = true, null = true)

    boys_6_fee = models.IntegerField(default=0)
    boys_7_fee = models.IntegerField(default=0)
    boys_8_fee = models.IntegerField(default=0)
    boys_9_fee = models.IntegerField(default=0)
    boys_10_fee = models.IntegerField(default=0)
    boys_11_fee = models.IntegerField(default=0)
    boys_12_fee = models.IntegerField(default=0)
    boys_13_fee = models.IntegerField(default=0)
    boys_14_fee = models.IntegerField(default=0)
    boys_15_fee = models.IntegerField(default=0)
    boys_16_fee = models.IntegerField(default=0)
    men_17_24_fee = models.IntegerField(default=0)
    men_25_29_fee = models.IntegerField(default=0)
    men_30_34_fee = models.IntegerField(default=0)
    men_35_over_fee = models.IntegerField(default=0)

    girls_7_fee = models.IntegerField(default=0)
    girls_8_fee = models.IntegerField(default=0)
    girls_9_fee = models.IntegerField(default=0)
    girls_10_fee =models.IntegerField(default=0)
    girls_11_fee =models.IntegerField(default=0)
    girls_12_fee =models.IntegerField(default=0)
    girls_13_fee =models.IntegerField(default=0)
    girls_14_fee =models.IntegerField(default=0)
    girls_15_fee =models.IntegerField(default=0)
    girls_16_fee =models.IntegerField(default=0)
    women_17_24_fee = models.IntegerField(default=0)
    women_25_over_fee = models.IntegerField(default=0)

    men_junior_fee = models.IntegerField(default=0)
    men_u23_fee = models.IntegerField(default=0)
    men_elite_fee = models.IntegerField(default=0)

    women_junior_fee =models.IntegerField(default=0)
    women_u23_fee = models.IntegerField(default=0)
    women_elite_fee = models.IntegerField(default=0)

    cr_boys_12_and_under_fee = models.IntegerField(default=0)
    cr_boys_13_14_fee = models.IntegerField(default=0)
    cr_boys_15_16_fee = models.IntegerField(default=0)

    cr_men_17_24_fee = models.IntegerField(default=0)
    cr_men_25_29_fee = models.IntegerField(default=0)
    cr_men_30_34_fee = models.IntegerField(default=0)
    cr_men_35_39_fee = models.IntegerField(default=0)
    cr_men_40_49_fee = models.IntegerField(default=0)
    cr_men_50_and_over_fee = models.IntegerField(default=0)
    
    cr_girls_12_and_under_fee = models.IntegerField(default=0)
    cr_girls_13_16_fee = models.IntegerField(default=0)
    cr_women_17_29_fee = models.IntegerField(default=0)
    cr_women_30_39_fee = models.IntegerField(default=0)
    cr_women_40_and_over_fee = models.IntegerField(default=0)

    is_enabled = models.BooleanField(default=true)

    created = models.DateField(auto_now_add=True, null=True)
    updated = models.DateField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.event_name
    
    class Meta:
        verbose_name = "Kategorie a startovné"
        verbose_name_plural = 'Kategorie a startovné'
    
    
class Event(models.Model):
    """ class for event """

    EVENT_TYPE = (('Mistrovství ČR jednotlivců', 'Mistrovství ČR jednotlivců'),
                  ('Mistrovství ČR družstev', 'Mistrovství ČR družstev'), ('Český pohár', 'Český pohár'),
                  ('Česká liga', 'Česká liga'),
                  ('Moravská liga', 'Moravská liga'), ('Volný závod', 'Volný závod'),
                  ('Nebodovaný závod', 'Nebodovaný závod'),)

    RACE_SYSTEM = (('3 základní rozjíždky a KO system', '3 základní rozjíždky a KO system'), ('5 základních rozjíždek a KO system', '5 základních rozjíždek a KO system'))

    name = models.CharField(max_length=255, blank=False)
    date = models.DateField(null=True, blank=True)

    organizer = models.ForeignKey(Club, related_name='club', null=True, on_delete=models.SET_NULL)

    type_for_ranking = models.CharField(max_length=100, choices=EVENT_TYPE, default="Volný závod")

    # classes_code = models.IntegerField(default = 3)
    classes_and_fees_like = models.ForeignKey(EntryClasses,  default = 6, on_delete=models.SET_DEFAULT, blank=True)

    is_uci_race = models.BooleanField(default=False)

    pcp = models.ForeignKey(Commissar, related_name="PCP", on_delete=models.SET_NULL, blank=True, null=True)
    pcp_assist = models.ForeignKey(Commissar, related_name="PCP_asist", on_delete=models.SET_NULL, blank=True, null=True)
    director = models.CharField(max_length=255, null=True, blank=True)

    reg_open_from = models.DateField(default='2021-04-01')
    reg_open_to = models.DateField(default='2021-12-31')
    reg_open = models.BooleanField(default=True)

    system = models.CharField(choices=RACE_SYSTEM, default='3 základní rozjíždky a KO system', max_length=100, blank=True, null=True)
    prices = RichTextField(max_length=10000, blank=True, null=True)
    timeschedule = RichTextField(max_length=10000, blank=True, null=True)
    notes = RichTextField(max_length=10000, blank=True, null=True)

    commission_fee = models.IntegerField(default=0)

    bem_entries = models.FileField(upload_to='static/bem_entries', null = True, blank = True)
    bem_entries_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    bem_riders_list = models.FileField(upload_to='static/bem_riders', null = True, blank = True)
    bem_riders_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    full_results_path = models.FileField(upload_to='static/full_results', null = True, blank = True)
    full_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    fast_riders_path = models.FileField(upload_to='static/full_results', null = True, blank = True)
    fast_riders_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    xml_results = models.FileField(upload_to='static/results', null=True, blank=True)
    xml_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    created = models.DateField(auto_now_add=True, null=True)
    updated = models.DateField(auto_now=True, null=True, blank=True)

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

# vymazání xml výsledků při aktualizaci
@receiver(pre_save, sender=Event)
def delete_xml_results_file (sender, instance, **kwargs):
    if instance.pk:
        try:
            old_xml = Event.objects.get(pk=instance.pk).xml_results
        except Event.DoesNotExist:
            return
        else:
            new_xml = instance.xml_results
            if old_xml and old_xml.url != new_xml.url:
                try:
                    old_xml.delete(save=False)
                except Exception as e:
                    pass
pre_save.connect(delete_xml_results_file, sender=Event)

# vymazání celkových výsledků při aktualizaci
@receiver(pre_save, sender=Event)
def delete_full_results_file (sender, instance, **kwargs):
    if instance.pk:
        try:
            old_full_results_path = Event.objects.get(pk=instance.pk).full_results_path
        except Event.DoesNotExist:
            return
        else:
            new_full_results_path = instance.full_results_path
            if old_full_results_path and old_full_results_path.url != new_full_results_path.url:
                old_full_results_path.delete(save=False)
pre_save.connect(delete_full_results_file, sender=Event)

# vymazání nejrychlejších jezdců
@receiver(pre_save, sender=Event)
def delete_fast_riders_file (sender, instance, **kwargs):
    if instance.pk:
        try:
            old_fast_riders_path = Event.objects.get(pk=instance.pk).fast_riders_path
        except Event.DoesNotExist:
            return
        else:
            new_fast_riders_path = instance.fast_riders_path
            if old_fast_riders_path and old_fast_riders_path.url != new_fast_riders_path.url:
                old_fast_riders_path.delete(save=False)
pre_save.connect(delete_fast_riders_file, sender=Event)

# nastavení provize Asociace klubů
@receiver(pre_save, sender=Event)
def commission_fee (sender, instance, **kwargs):
    if instance.commission_fee == 0:
        if instance.type_for_ranking =="Český pohár" or instance.type_for_ranking =="Česká liga" or instance.type_for_ranking =="Moravská liga":
            instance.commission_fee=20
        else:
            instance.commission_fee=5
pre_save.connect(commission_fee, sender=Event)


class Result(models.Model):
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    event_type = models.CharField(max_length=255, null=True, blank=True)
    organizer = models.CharField(max_length=100, null=True, blank=True)
    rider = models.IntegerField(default=0)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    club = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    place = models.IntegerField(default=0)
    points = models.IntegerField(default=0)
    is_20 = models.BooleanField(default=1)
    marked_20 = models.BooleanField(default=0)
    marked_24 = models.BooleanField(default=0)

    class Meta:
        verbose_name = "Výsledek"
        verbose_name_plural = "Výsledky"

    def __str__(self):
        return self.name + " " + str(self.last_name) + " " + self.first_name + " " + self.category