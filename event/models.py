from django.db import models
import uuid
from django.core.exceptions import ValidationError
from club.models import Club
from commissar.models import Commissar
from rider.models import Rider
from accounts.models import Account
from django_ckeditor_5.fields import CKEditor5Field
from datetime import date
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.db.models import F, Q
import datetime
from django.utils.translation import gettext_lazy as _
from bmx.html_sanitizer import sanitize_rich_html


# Create your models here.

def normalize_uci_id(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())

class SeasonSettings(models.Model):
    year = models.IntegerField(default=2024)
    qualify_to_cn = models.IntegerField (default=2)
    best_cup = models.IntegerField(default=8)
    best_league = models.IntegerField(default=10)
    beginners_allowed = models.BooleanField(default=True)
    rider_stats_monthly_price = models.IntegerField(default=50)
    trainer_club_stats_monthly_price = models.IntegerField(default=250)
    trainer_extended_monthly_price = models.IntegerField(default=500)
    transponder_price = models.IntegerField(default=1900)
    bmx_rules_link = models.URLField(max_length=500, blank=True, null=True)

    def __str__(self):
        return str(self.year)

    class Meta:
        verbose_name = "Nastavení sezony"
        verbose_name_plural = 'Nastavení sezony'

class EntryClasses(models.Model):
    event_name = models.CharField(max_length=200)

    beginners_1 = models.CharField(max_length=50, blank=True, null=True)
    beginners_2 = models.CharField(max_length=50, blank=True, null=True)
    beginners_3 = models.CharField(max_length=50, blank=True, null=True)
    beginners_4 = models.CharField(max_length=50, blank=True, null=True)

    boys_6 = models.CharField(max_length=50, blank=True, null=True)
    boys_7 = models.CharField(max_length=50, blank=True, null=True)
    boys_8 = models.CharField(max_length=50, blank=True, null=True)
    boys_9 = models.CharField(max_length=50, blank=True, null=True)
    boys_10 = models.CharField(max_length=50, blank=True, null=True)
    boys_11 = models.CharField(max_length=50, blank=True, null=True)
    boys_12 = models.CharField(max_length=50, blank=True, null=True)
    boys_13 = models.CharField(max_length=50, blank=True, null=True)
    boys_14 = models.CharField(max_length=50, blank=True, null=True)
    boys_15 = models.CharField(max_length=50, blank=True, null=True)
    boys_16 = models.CharField(max_length=50, blank=True, null=True)
    men_17_24 = models.CharField(max_length=50, blank=True, null=True)
    men_25_29 = models.CharField(max_length=50, blank=True, null=True)
    men_30_34 = models.CharField(max_length=50, blank=True, null=True)
    men_35_over = models.CharField(max_length=50, blank=True, null=True)

    girls_6 = models.CharField(max_length=50, blank=True, null=True)
    girls_7 = models.CharField(max_length=50, blank=True, null=True)
    girls_8 = models.CharField(max_length=50, blank=True, null=True)
    girls_9 = models.CharField(max_length=50, blank=True, null=True)
    girls_10 = models.CharField(max_length=50, blank=True, null=True)
    girls_11 = models.CharField(max_length=50, blank=True, null=True)
    girls_12 = models.CharField(max_length=50, blank=True, null=True)
    girls_13 = models.CharField(max_length=50, blank=True, null=True)
    girls_14 = models.CharField(max_length=50, blank=True, null=True)
    girls_15 = models.CharField(max_length=50, blank=True, null=True)
    girls_16 = models.CharField(max_length=50, blank=True, null=True)
    women_17_24 = models.CharField(max_length=50, blank=True, null=True)
    women_25_over = models.CharField(max_length=50, blank=True, null=True)

    men_junior = models.CharField(max_length=50, blank=True, null=True)
    men_u23 = models.CharField(max_length=50, blank=True, null=True)
    men_elite = models.CharField(max_length=50, blank=True, null=True)

    women_junior = models.CharField(max_length=50, blank=True, null=True)
    women_u23 = models.CharField(max_length=50, blank=True, null=True)
    women_elite = models.CharField(max_length=50, blank=True, null=True)

    cr_boys_12_and_under = models.CharField(max_length=50, blank=True, null=True)
    cr_boys_13_14 = models.CharField(max_length=50, blank=True, null=True)
    cr_boys_15_16 = models.CharField(max_length=50, blank=True, null=True)

    cr_men_17_24 = models.CharField(max_length=50, blank=True, null=True)
    cr_men_25_29 = models.CharField(max_length=50, blank=True, null=True)
    cr_men_30_34 = models.CharField(max_length=50, blank=True, null=True)
    cr_men_35_39 = models.CharField(max_length=50, blank=True, null=True)
    cr_men_40_44 = models.CharField(max_length=50, blank=True, null=True)
    cr_men_45_49 = models.CharField(max_length=50, blank=True, null=True)
    cr_men_50_and_over = models.CharField(max_length=50, blank=True, null=True)

    cr_girls_12_and_under = models.CharField(max_length=50, blank=True, null=True)
    cr_girls_13_16 = models.CharField(max_length=50, blank=True, null=True)
    cr_women_17_29 = models.CharField(max_length=50, blank=True, null=True)
    cr_women_30_39 = models.CharField(max_length=50, blank=True, null=True)
    cr_women_40_and_over = models.CharField(max_length=50, blank=True, null=True)

    beginners_1_fee = models.IntegerField(default=0)
    beginners_2_fee = models.IntegerField(default=0)
    beginners_3_fee = models.IntegerField(default=0)
    beginners_4_fee = models.IntegerField(default=0)

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

    girls_6_fee = models.IntegerField(default=0)
    girls_7_fee = models.IntegerField(default=0)
    girls_8_fee = models.IntegerField(default=0)
    girls_9_fee = models.IntegerField(default=0)
    girls_10_fee = models.IntegerField(default=0)
    girls_11_fee = models.IntegerField(default=0)
    girls_12_fee = models.IntegerField(default=0)
    girls_13_fee = models.IntegerField(default=0)
    girls_14_fee = models.IntegerField(default=0)
    girls_15_fee = models.IntegerField(default=0)
    girls_16_fee = models.IntegerField(default=0)
    women_17_24_fee = models.IntegerField(default=0)
    women_25_over_fee = models.IntegerField(default=0)

    men_junior_fee = models.IntegerField(default=0)
    men_u23_fee = models.IntegerField(default=0)
    men_elite_fee = models.IntegerField(default=0)

    women_junior_fee = models.IntegerField(default=0)
    women_u23_fee = models.IntegerField(default=0)
    women_elite_fee = models.IntegerField(default=0)

    cr_boys_12_and_under_fee = models.IntegerField(default=0)
    cr_boys_13_14_fee = models.IntegerField(default=0)
    cr_boys_15_16_fee = models.IntegerField(default=0)

    cr_men_17_24_fee = models.IntegerField(default=0)
    cr_men_25_29_fee = models.IntegerField(default=0)
    cr_men_30_34_fee = models.IntegerField(default=0)
    cr_men_35_39_fee = models.IntegerField(default=0)
    cr_men_40_44_fee = models.IntegerField(default=0)
    cr_men_45_49_fee = models.IntegerField(default=0)
    cr_men_50_and_over_fee = models.IntegerField(default=0)

    cr_girls_12_and_under_fee = models.IntegerField(default=0)
    cr_girls_13_16_fee = models.IntegerField(default=0)
    cr_women_17_29_fee = models.IntegerField(default=0)
    cr_women_30_39_fee = models.IntegerField(default=0)
    cr_women_40_and_over_fee = models.IntegerField(default=0)

    is_enabled = models.BooleanField(default=True)

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
                  ('Mistrovství ČR družstev', 'Mistrovství ČR družstev'),
                  ('Český pohár', 'Český pohár'),
                  ('Česká liga', 'Česká liga'),
                  ('Moravská liga', 'Moravská liga'),
                  ('Volný závod', 'Volný závod'),
                  ('Evropský pohár', 'Evropský pohár'),
                  ('Mistrovství Evropy', 'Mistrovství Evropy'),
                  ('Mistrovství světa', 'Mistrovství světa'),
                  ('Světový pohár', 'Světový pohár'),
                  ('Nebodovaný závod', 'Nebodovaný závod'),)

    RACE_SYSTEM = (('3 základní rozjíždky a KO system', '3 základní rozjíždky a KO system'),
                   ('5 základních rozjíždek a KO system', '5 základních rozjíždek a KO system'),
                   ( "LCQ","LCQ"),)

    name = models.CharField(max_length=255, blank=False, help_text="Název závodu")
    date = models.DateField(null=True, blank=True, db_index=True)

    double_race = models.BooleanField(default=False)

    organizer = models.ForeignKey(Club, related_name='club', null=True, on_delete=models.SET_NULL)

    type_for_ranking = models.CharField(max_length=100, choices=EVENT_TYPE, default="Volný závod")

    # classes_code = models.IntegerField(default = 3)
    classes_and_fees_like = models.ForeignKey(EntryClasses, on_delete=models.SET_NULL, blank=True, null=True)

    is_uci_race = models.BooleanField(default=False)

    pcp = models.ForeignKey(Commissar, related_name="PCP", on_delete=models.SET_NULL, blank=True, null=True, help_text="Hlavní rozhodčí")
    pcp_assist = models.ForeignKey(Commissar, related_name="PCP_asist", on_delete=models.SET_NULL, blank=True,
                                   null=True, help_text="Asistent hlavního rozhodčího")
    start_commissar = models.ForeignKey(
        Commissar,
        related_name="start_commissar_events",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Start commissar",
    )
    director = models.CharField(max_length=255, null=True, blank=True)

    reg_open_from = models.DateTimeField(null=True, blank=True)
    reg_open_to = models.DateTimeField(null=True, blank=True)
    reg_open = models.BooleanField(default=True)

    system = models.CharField(choices=RACE_SYSTEM, default='3 základní rozjíždky a KO system', max_length=100,
                              blank=True, null=True)
    commission_fee = models.IntegerField(default=5)

    youtube_link = models.CharField(max_length=255, null=True, blank=True)

    proposition = models.FileField(upload_to='propositions/', null=True, blank=True)
    proposition_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    series = models.FileField(upload_to='series/', null=True, blank=True)
    series_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    # file for BMX EVENT MANAGER
    bem_entries = models.FileField(upload_to='bem_entries/', null=True, blank=True)
    bem_entries_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    bem_riders_list = models.FileField(upload_to='bem_riders/', null=True, blank=True)
    bem_riders_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    bem_backup = models.FileField(upload_to='bem_backup/', null=True, blank=True)
    bem_backup_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    # for events with 2 block
    bem_backup_2 = models.FileField(upload_to='bem_backup/', null=True, blank=True)
    bem_backup_2_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    full_results = models.FileField(upload_to='full_results/', null=True, blank=True)
    full_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    html_results = models.FileField(upload_to='html_results/', null=True, blank=True)
    html_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    fast_riders = models.FileField(upload_to='full_results/', null=True, blank=True)
    fast_riders_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    xls_results = models.FileField(upload_to='xls_results/', null=True, blank=True)
    xls_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    # file for RACE EVENT MANAGER
    rem_entries = models.FileField(upload_to='rem_entries/', null=True, blank=True)
    rem_entries_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    rem_riders_list = models.FileField(upload_to='rem_riders/', null=True, blank=True)
    rem_riders_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    rem_results = models.FileField(upload_to='rem_results/', null=True, blank=True)
    rem_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    # file for EUROPEAN CUP
    ec_file = models.FileField(upload_to='ec-files/', null=True, blank=True)
    ec_file_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    ec_insurance_file = models.FileField(upload_to='ec-files/', null=True, blank=True)
    ec_insurance_file_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    price_of_insurance = models.IntegerField(default = 0)

    #ID pro výsledkový servis Českého svazu cyklisitiky
    ccf_id = models.IntegerField(default = 0, help_text="ID závodu na portálu ČSC")
    ccf_created = models.DateField(auto_now_add=True, null=True)
    ccf_uploaded = models.BooleanField(default=False)

    uci_event_code = models.CharField(
        _("UCI event code"),
        max_length=64,
        blank=True,
        default="",
        help_text=_("Unique UCI event code"),
    )
    uci_code_women_elite = models.CharField(_("UCI code women elite"), max_length=64, blank=True, default="")
    uci_code_men_elite = models.CharField(_("UCI code men elite"), max_length=64, blank=True, default="")
    uci_code_women_under_23 = models.CharField(_("UCI code women under 23"), max_length=64, blank=True, default="")
    uci_code_men_under_23 = models.CharField(_("UCI code men under 23"), max_length=64, blank=True, default="")
    uci_code_women_junior = models.CharField(_("UCI code women junior"), max_length=64, blank=True, default="")
    uci_code_men_junior = models.CharField(_("UCI code men junior"), max_length=64, blank=True, default="")

    uec_link = models.URLField(max_length=500, blank=True, null=True, help_text="Externí registrace na UEC")
    flexibee_export = models.FileField(upload_to='invoices/xml/', null=True, blank=True)

    created = models.DateField(auto_now_add=True, null=True)
    updated = models.DateField(auto_now=True, null=True, blank=True)

    canceled = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    @staticmethod
    def _file_url(field):
        try:
            return field.url if field else ""
        except (ValueError, OSError):
            return ""

    @property
    def proposition_url(self):
        return self._file_url(self.proposition)

    @property
    def series_url(self):
        return self._file_url(self.series)

    @property
    def html_results_url(self):
        return self._file_url(self.html_results)

    @property
    def full_results_url(self):
        return self._file_url(self.full_results)

    @property
    def flexibee_export_url(self):
        return self._file_url(self.flexibee_export)

    def events_in_year(self, year):
        year = date.today().year
        events_in_year = Event.objects.filter(date__year=year).count()
        return events_in_year

    def is_beginners_event(self):
        if self.type_for_ranking =="Mistrovství ČR jednotlivců" or self.type_for_ranking == "Mistrovství ČR družstev" or self.type_for_ranking=="Český pohár" or self.type_for_ranking=="Evropský pohár" or self.type_for_ranking=="Mistrovství Evropy" or self.type_for_ranking=="Mistrovství světa" or self.type_for_ranking=="Světový pohár":
            return False
        if not self.classes_and_fees_like:
            return False
        elif not self.classes_and_fees_like.beginners_1:
            return False
        else:
            return True

    def clean(self):
        super().clean()

        assignments = {
            "pcp": self.pcp,
            "pcp_assist": self.pcp_assist,
            "start_commissar": self.start_commissar,
        }
        selected_ids = [commissar.id for commissar in assignments.values() if commissar is not None]
        if len(selected_ids) != len(set(selected_ids)):
            raise ValidationError(
                _("Jeden rozhodčí nemůže být v jednom závodě nasazen do více rolí současně.")
            )

    class Meta:
        verbose_name = "Závod"
        verbose_name_plural = 'Závody'
        ordering = ['-date', ]
        constraints = [
            models.CheckConstraint(
                condition=Q(pcp__isnull=True) | Q(pcp_assist__isnull=True) | ~Q(pcp=F("pcp_assist")),
                name="event_distinct_pcp_and_pcp_assist",
            ),
            models.CheckConstraint(
                condition=Q(pcp__isnull=True) | Q(start_commissar__isnull=True) | ~Q(pcp=F("start_commissar")),
                name="event_distinct_pcp_and_start_commissar",
            ),
            models.CheckConstraint(
                condition=Q(pcp_assist__isnull=True) | Q(start_commissar__isnull=True) | ~Q(pcp_assist=F("start_commissar")),
                name="event_distinct_pcp_assist_and_start_commissar",
            ),
        ]


class EventProposition(models.Model):
    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="structured_proposition",
    )
    venue_name = models.CharField(max_length=255, blank=True, default="")
    venue_address = models.CharField(max_length=255, blank=True, default="")
    office_hours = models.CharField(max_length=255, blank=True, default="")
    contact_name = models.CharField(max_length=255, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")
    contact_phone = models.CharField(max_length=100, blank=True, default="")
    summary = CKEditor5Field(max_length=4000, blank=True, null=True, default="", config_name="event_proposition")
    schedule = CKEditor5Field(max_length=8000, blank=True, null=True, default="", config_name="event_proposition")
    categories = CKEditor5Field(max_length=6000, blank=True, null=True, default="", config_name="event_proposition")
    registration_info = CKEditor5Field(max_length=6000, blank=True, null=True, default="", config_name="event_proposition")
    awards = CKEditor5Field(max_length=4000, blank=True, null=True, default="", config_name="event_proposition")
    accommodation = CKEditor5Field(max_length=4000, blank=True, null=True, default="", config_name="event_proposition")
    additional_info = CKEditor5Field(max_length=6000, blank=True, null=True, default="", config_name="event_proposition")
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_event_propositions",
    )
    updated_by = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_event_propositions",
    )
    created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = "Formulářová propozice"
        verbose_name_plural = "Formulářové propozice"
        ordering = ["-updated", "-created"]

    def __str__(self):
        return f"Propozice: {self.event.name}"

    def save(self, *args, **kwargs):
        self.summary = sanitize_rich_html(self.summary)
        self.schedule = sanitize_rich_html(self.schedule)
        self.categories = sanitize_rich_html(self.categories)
        self.registration_info = sanitize_rich_html(self.registration_info)
        self.awards = sanitize_rich_html(self.awards)
        self.accommodation = sanitize_rich_html(self.accommodation)
        self.additional_info = sanitize_rich_html(self.additional_info)
        super().save(*args, **kwargs)


# Smazání starých souborů při aktualizaci — jeden signal, jeden DB dotaz místo 7
@receiver(pre_save, sender=Event)
def delete_old_event_files(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = Event.objects.get(pk=instance.pk)
    except Event.DoesNotExist:
        return

    def _delete_if_url_changed(old_field, new_field):
        try:
            old_name = getattr(old_field, "name", "") or ""
            new_name = getattr(new_field, "name", "") or ""
            if old_field and old_name != new_name:
                old_field.delete(save=False)
        except Exception:
            pass

    def _delete_if_changed(old_field, new_field):
        try:
            if old_field and old_field != new_field:
                old_field.delete(save=False)
        except Exception:
            pass

    _delete_if_url_changed(old.xls_results, instance.xls_results)
    _delete_if_changed(old.bem_backup, instance.bem_backup)
    _delete_if_changed(old.bem_backup_2, instance.bem_backup_2)
    _delete_if_url_changed(old.full_results, instance.full_results)
    _delete_if_url_changed(old.fast_riders, instance.fast_riders)
    _delete_if_url_changed(old.series, instance.series)
    _delete_if_url_changed(old.proposition, instance.proposition)




# nastavení provize Asociace klubů
@receiver(pre_save, sender=Event)
def commission_fee(sender, instance, **kwargs):
    if instance.commission_fee == 0:
        if instance.type_for_ranking == "Český pohár" or instance.type_for_ranking == "Česká liga" or instance.type_for_ranking == "Moravská liga":
            instance.commission_fee = 20
        else:
            instance.commission_fee = 5




class Result(models.Model):
    """ Model for results """
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True)
    date = models.DateField(null=True, blank=True)
    event_type = models.CharField(max_length=255, null=True, blank=True)
    organizer = models.CharField(max_length=100, null=True, blank=True)
    rider = models.ForeignKey(Rider, to_field='uci_id', db_constraint=False, on_delete=models.SET_NULL, null=True, blank=True)
    country = models.CharField(max_length=3, null=True, blank=True, default="CZE")
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    club = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    place = models.IntegerField(default=0)
    points = models.IntegerField(default=0)
    is_beginner = models.BooleanField(default=False)
    is_20 = models.BooleanField(default=True)
    marked_20 = models.BooleanField(default=0)
    marked_24 = models.BooleanField(default=0)

    class Meta:
        verbose_name = "Výsledek"
        verbose_name_plural = "Výsledky"

    def __str__(self):
        event_name = self.event.name if self.event else "Bez závodu"
        return f"{event_name} – {self.last_name} {self.first_name} ({self.category})"


@receiver(post_save, sender=Result)
def sync_rider_categories_from_result(sender, instance, **kwargs):
    """Zapne rider.is_20 / rider.is_24 podle prvního uloženého výsledku."""
    if not instance.rider_id or instance.is_beginner:
        return

    if instance.is_20:
        Rider.objects.filter(uci_id=instance.rider_id, is_20=False).update(is_20=True)
    else:
        Rider.objects.filter(uci_id=instance.rider_id, is_24=False).update(is_24=True)


class RaceRun(models.Model):
    result = models.ForeignKey(Result, on_delete=models.SET_NULL, related_name="runs", null=True, blank=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, null=True, blank=True)
    rider = models.ForeignKey(Rider, on_delete=models.SET_NULL, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    is_beginner = models.BooleanField(default=False)
    is_20 = models.BooleanField(null=True, blank=True)
    round_type = models.CharField(max_length=20)  # např. MOTO, FINAL, F2, ...
    round_number = models.IntegerField(null=True, blank=True)  # např. 1 až 8 pro MOTO, None pro FINAL
    heat_code = models.CharField(max_length=50, null=True, blank=True)  # např. 38, F1 (A)
    plate = models.CharField(max_length=20, null=True, blank=True)

    gate = models.IntegerField(null=True, blank=True)
    lane = models.IntegerField(null=True, blank=True)
    place = models.CharField(max_length=10, null=True, blank=True)  # např. "1st", "DNF"
    race_points = models.IntegerField(null=True, blank=True)
    moto_points = models.IntegerField(null=True, blank=True)
    qualified_to_next_round = models.BooleanField(null=True, blank=True)

    hill_time = models.FloatField(null=True, blank=True)     # ⛰️ Inter1 / čas na kopci (start hill)
    finish_time = models.FloatField(null=True, blank=True)   # 🏁 čas v cíli

    split_1 = models.FloatField(null=True, blank=True)       # 🌀 Inter2 / mezičas z první zatáčky
    split_2 = models.FloatField(null=True, blank=True)
    split_3 = models.FloatField(null=True, blank=True)
    split_4 = models.FloatField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Jízda závodníka"
        verbose_name_plural = "Jízdy závodníka"

    def __str__(self):
        label = self.result or self.rider or self.plate or "RaceRun"
        return f"{label} – {self.round_type} {self.round_number or ''} ({self.place})"


class Entry(models.Model):
    """ Models for entries to the race for Czech riders """
    user = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, blank=True) # to_field='id', db_column='event'
    transaction_id = models.CharField(max_length=255, default="", null=True, blank=True)
    rider = models.ForeignKey(Rider, db_constraint=False, on_delete=models.SET_NULL, null=True, )
    is_beginner = models.BooleanField(default=False)
    is_20 = models.BooleanField(default=False)
    is_24 = models.BooleanField(default=False)
    class_beginner = models.CharField(max_length=255, default="", null=True, blank=True)
    class_20 = models.CharField(max_length=255, default="", null=True, blank=True)
    class_24 = models.CharField(max_length=255, default="", null=True, blank=True)
    fee_beginner = models.IntegerField(null=True, blank=True, default=0)
    fee_20 = models.IntegerField(null=True, blank=True, default=0)
    fee_24 = models.IntegerField(null=True, blank=True, default=0)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)
    payment_complete = models.BooleanField(default=False)
    checkout = models.BooleanField(default=False)
    date_of_payment = models.DateField(auto_now_add=True, null=True)
    customer_name = models.CharField(max_length=100, null=True, blank=True, default="")
    customer_email = models.CharField(max_length=100, null=True, blank=True, default="")

    created = models.DateField(auto_now_add=True, null=True)
    updated = models.DateField(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = "Registrace"
        verbose_name_plural = 'Registrace'
        indexes = [
            models.Index(fields=["event", "payment_complete", "checkout"], name="event_entry_evt_pay_chk"),
            models.Index(fields=["user", "payment_complete"], name="event_entry_user_pay"),
            models.Index(fields=["transaction_date"], name="event_entry_tx_date"),
        ]

    def __str__(self):
        return f"{self.rider} - {self.event}"

@receiver(post_save, sender=Entry)
@receiver(post_delete, sender=Entry)
def invalidate_cache_on_entry_change(sender, instance, **kwargs):
    # Invaliduje cache seznamu aktivních jezdců (sdílená data pro všechny eventy)
    cache.delete("active_riders")

class EntryForeign(models.Model):
    """ Model for foreign riders entries """

    transaction_id = models.CharField(max_length=255, default="")
    event = models.ForeignKey(Event, to_field='id', db_column='event', on_delete=models.SET_NULL, null=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    uci_id = models.CharField(max_length=20)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20)
    nationality = models.CharField(max_length=3)
    club = models.CharField(max_length=50)
    transponder = models.CharField(max_length=10)
    transponder_20 = models.CharField(max_length=10, null=True, blank=True, default="")
    transponder_24 = models.CharField(max_length=10, null=True, blank=True, default="")
    plate = models.CharField(max_length=20, null=True, blank=True, default="")
    is_20 = models.BooleanField(default=False)
    is_24 = models.BooleanField(default=False)
    is_elite = models.BooleanField(default=False)
    class_20 = models.CharField(max_length=255, default="", null=True, blank=True)
    class_24 = models.CharField(max_length=255, default="", null=True, blank=True)
    fee_20 = models.IntegerField(null=True, blank=True, default=0)
    fee_24 = models.IntegerField(null=True, blank=True, default=0)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)
    payment_complete = models.BooleanField(default=False)
    checkout = models.BooleanField(default=False)
    date_of_payment = models.DateField(auto_now_add=True, null=True)
    customer_name = models.CharField(max_length=100, null=True, blank=True, default="")
    customer_email = models.CharField(max_length=100, null=True, blank=True, default="")

    def save(self, *args, **kwargs):
        self.uci_id = normalize_uci_id(self.uci_id)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Registrace zahraničních jezdců"
        verbose_name_plural = 'Registrace zahraničních jezdců'
        indexes = [
            models.Index(fields=["event", "payment_complete", "checkout"], name="event_entryfor_evt_pay_chk"),
            models.Index(fields=["uci_id"], name="event_entryfor_uci"),
            models.Index(fields=["transaction_date"], name="event_entryfor_tx_date"),
        ]


class DebetTransaction (models.Model):
    """ Model for transactions """
    user = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    entry = models.ForeignKey(Entry, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.IntegerField(default=0)
    payment_valid = models.BooleanField(default=True)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Debetní transakce"
        verbose_name_plural = 'Debetní transakce'
        indexes = [
            models.Index(fields=["user", "transaction_date"], name="event_debet_user_date"),
            models.Index(fields=["entry"], name="event_debet_entry"),
        ]

    def __str__(self):
        user = self.user if self.user else "Neznámý uživatel"
        event = self.entry.event if self.entry else "Neznámý závod"
        rider = self.entry.rider if self.entry else "Neznámý jezdec"
        return f"{user} - {event} - {rider}"


class CreditTransaction (models.Model):
    """ Model for transactions """
    user = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.IntegerField(default=0)
    transaction_id = models.CharField(max_length=255, default="")
    payment_intent = models.CharField(max_length=255, default="")
    payment_complete = models.BooleanField(default=False)
    transaction_date = models.DateTimeField(auto_now_add=True, null=True)
    uuid = models.UUIDField(default=uuid.uuid4, unique=False, editable=False)
    

    class Meta:
        verbose_name = "Kreditní transakce"
        verbose_name_plural = 'Kreditní transakce'
        indexes = [
            models.Index(fields=["user", "payment_complete", "transaction_date"], name="event_credit_user_pay_date"),
            models.Index(fields=["transaction_id"], name="event_credit_tx_id"),
        ]
    
    def __str__(self):
        user = self.user if self.user else "Neznámý uživatel"
        return f"{user} - {self.amount} Kč"
    
@receiver(post_save, sender=CreditTransaction)
def update_user_balance(sender, instance, **kwargs):
    """ Před uložením transakce přepočítá kredit uživatele """
    if instance.user:
        from .credit import calculate_user_balance  # Použití relativního importu
        new_balance = calculate_user_balance(instance.user.id)  # Spočítá nový kredit
        instance.user.credit = new_balance  # Aktualizuje kredit
        instance.user.save()  # Uloží změnu do modelu Account


@receiver(post_delete, sender=CreditTransaction)
def update_user_balance_after_delete(sender, instance, **kwargs):
    """ Po smazání transakce přepočítá kredit uživatele """
    if instance.user:
        from .credit import calculate_user_balance  # Použití relativního importu
        new_balance = calculate_user_balance(instance.user.id)  # Spočítá nový kredit
        instance.user.credit = new_balance  # Aktualizuje kredit
        instance.user.save()  # Uloží změnu do modelu Account


class StripeFee (models.Model):
    """ Model for card transaction fee"""
    date = models.DateField(default=datetime.date.today)
    fee = models.DecimalField(default = 0, decimal_places=2, max_digits = 10)
    created = models.DateTimeField(auto_now_add = True, null=True)

    class Meta:
        verbose_name = "Karetní poplatek"
        verbose_name_plural = 'Karetní poplatky (STRIPE)'
        indexes = [
            models.Index(fields=["date"], name="event_stripefee_date"),
        ]
