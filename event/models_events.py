from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from django_ckeditor_5.fields import CKEditor5Field

from accounts.models import Account
from bmx.html_sanitizer import sanitize_rich_html
from club.models import Club
from commissar.models import Commissar


class SeasonSettings(models.Model):
    year = models.IntegerField(default=2024)
    qualify_to_cn = models.IntegerField(default=2)
    best_cup = models.IntegerField(default=8)
    best_league = models.IntegerField(default=10)
    beginners_allowed = models.BooleanField(default=True)
    mcr_club_registration_open = models.BooleanField(default=True)
    rider_stats_monthly_price = models.IntegerField(default=50)
    trainer_club_stats_monthly_price = models.IntegerField(default=250)
    trainer_extended_monthly_price = models.IntegerField(default=500)
    mobile_app_annual_price = models.IntegerField(default=499)
    transponder_price = models.IntegerField(default=1900)
    bmx_rules_link = models.URLField(max_length=500, blank=True, null=True)

    def __str__(self):
        return str(self.year)

    class Meta:
        verbose_name = "Nastavení sezony"
        verbose_name_plural = "Nastavení sezony"


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
        verbose_name_plural = "Kategorie a startovné"


class EventType(models.TextChoices):
    """Typ závodu pro ranking. Hodnoty jsou české názvy uložené v DB
    a porovnávané napříč logikou — vždy používej tyto konstanty, ne literály."""

    MCR_JEDNOTLIVCU = "Mistrovství ČR jednotlivců"
    MCR_DRUZSTEV = "Mistrovství ČR družstev"
    CESKY_POHAR = "Český pohár"
    CESKA_LIGA = "Česká liga"
    MORAVSKA_LIGA = "Moravská liga"
    VOLNY_ZAVOD = "Volný závod"
    EVROPSKY_POHAR = "Evropský pohár"
    MISTROVSTVI_EVROPY = "Mistrovství Evropy"
    MISTROVSTVI_SVETA = "Mistrovství světa"
    SVETOVY_POHAR = "Světový pohár"
    NEBODOVANY_ZAVOD = "Nebodovaný závod"


class Event(models.Model):
    EVENT_TYPE = EventType.choices

    RACE_SYSTEM = (
        ("3 základní rozjíždky a KO system", "3 základní rozjíždky a KO system"),
        ("5 základních rozjíždek a KO system", "5 základních rozjíždek a KO system"),
        ("LCQ", "LCQ"),
    )

    name = models.CharField(max_length=255, blank=False, help_text="Název závodu")
    date = models.DateField(null=True, blank=True, db_index=True)
    double_race = models.BooleanField(default=False)
    organizer = models.ForeignKey(Club, related_name="club", null=True, on_delete=models.SET_NULL)
    type_for_ranking = models.CharField(max_length=100, choices=EventType.choices, default=EventType.VOLNY_ZAVOD)
    classes_and_fees_like = models.ForeignKey(EntryClasses, on_delete=models.SET_NULL, blank=True, null=True)
    is_uci_race = models.BooleanField(default=False)
    pcp = models.ForeignKey(
        Commissar,
        related_name="PCP",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Hlavní rozhodčí",
    )
    pcp_assist = models.ForeignKey(
        Commissar,
        related_name="PCP_asist",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Asistent hlavního rozhodčího",
    )
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
    reg_cancel_to = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Termín do kdy je možné odhlášení. Pokud není vyplněn, použije se konec registrace.",
    )
    reg_open = models.BooleanField(default=True)
    eshop_pickup_enabled = models.BooleanField(
        _("Výdej e-shop zboží"),
        default=False,
        help_text=_("Zaškrtněte pouze u závodů, kde bude možné předávat objednávky z e-shopu."),
    )
    eshop_pickup_location = models.CharField(_("Místo výdeje e-shopu"), max_length=160, blank=True)
    eshop_pickup_time = models.CharField(_("Čas výdeje e-shopu"), max_length=120, blank=True)
    eshop_pickup_note = models.TextField(_("Poznámka k výdeji e-shopu"), blank=True)
    system = models.CharField(
        choices=RACE_SYSTEM,
        default="3 základní rozjíždky a KO system",
        max_length=100,
        blank=True,
        null=True,
    )
    commission_fee = models.IntegerField(default=5)
    youtube_link = models.CharField(max_length=255, null=True, blank=True)
    proposition = models.FileField(upload_to="propositions/", null=True, blank=True)
    proposition_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    series = models.FileField(upload_to="series/", null=True, blank=True)
    series_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    bem_entries = models.FileField(upload_to="bem_entries/", null=True, blank=True)
    bem_entries_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    bem_riders_list = models.FileField(upload_to="bem_riders/", null=True, blank=True)
    bem_riders_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    bem_backup = models.FileField(upload_to="bem_backup/", null=True, blank=True)
    bem_backup_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    bem_backup_2 = models.FileField(upload_to="bem_backup/", null=True, blank=True)
    bem_backup_2_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    full_results = models.FileField(upload_to="full_results/", null=True, blank=True)
    full_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    html_results = models.FileField(upload_to="html_results/", null=True, blank=True)
    html_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    fast_riders = models.FileField(upload_to="full_results/", null=True, blank=True)
    fast_riders_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    xls_results = models.FileField(upload_to="xls_results/", null=True, blank=True)
    xls_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    rem_entries = models.FileField(upload_to="rem_entries/", null=True, blank=True)
    rem_entries_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    rem_riders_list = models.FileField(upload_to="rem_riders/", null=True, blank=True)
    rem_riders_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    rem_results = models.FileField(upload_to="rem_results/", null=True, blank=True)
    rem_results_uploaded = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    ec_file = models.FileField(upload_to="ec-files/", null=True, blank=True)
    ec_file_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    ec_insurance_file = models.FileField(upload_to="ec-files/", null=True, blank=True)
    ec_insurance_file_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    price_of_insurance = models.IntegerField(default=0)
    ccf_id = models.IntegerField(default=0, help_text="ID závodu na portálu ČSC")
    ccf_created = models.DateField(auto_now_add=True, null=True)
    ccf_uploaded = models.BooleanField(default=False)
    uci_event_code = models.CharField(_("UCI event code"), max_length=64, blank=True, default="", help_text=_("Unique UCI event code"))
    uci_code_women_elite = models.CharField(_("UCI code women elite"), max_length=64, blank=True, default="")
    uci_code_men_elite = models.CharField(_("UCI code men elite"), max_length=64, blank=True, default="")
    uci_code_women_under_23 = models.CharField(_("UCI code women under 23"), max_length=64, blank=True, default="")
    uci_code_men_under_23 = models.CharField(_("UCI code men under 23"), max_length=64, blank=True, default="")
    uci_code_women_junior = models.CharField(_("UCI code women junior"), max_length=64, blank=True, default="")
    uci_code_men_junior = models.CharField(_("UCI code men junior"), max_length=64, blank=True, default="")
    uec_link = models.URLField(max_length=500, blank=True, null=True, help_text="Externí registrace na UEC")
    flexibee_export = models.FileField(upload_to="invoices/xml/", null=True, blank=True)
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
        return Event.objects.filter(date__year=year).count()

    def is_beginners_event(self):
        if self.type_for_ranking in {
            EventType.MCR_JEDNOTLIVCU,
            EventType.MCR_DRUZSTEV,
            EventType.CESKY_POHAR,
            EventType.EVROPSKY_POHAR,
            EventType.MISTROVSTVI_EVROPY,
            EventType.MISTROVSTVI_SVETA,
            EventType.SVETOVY_POHAR,
        }:
            return False
        if not self.classes_and_fees_like:
            return False
        if not self.classes_and_fees_like.beginners_1:
            return False
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
            raise ValidationError(_("Jeden rozhodčí nemůže být v jednom závodě nasazen do více rolí současně."))

    class Meta:
        verbose_name = "Závod"
        verbose_name_plural = "Závody"
        ordering = ["-date"]
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


class EventPhoto(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="photos")
    photo = models.ImageField(upload_to="images/events/gallery/")
    caption = models.CharField(max_length=255, blank=True, default="")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Foto závodu"
        verbose_name_plural = "Fotogalerie závodů"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.event.name} – foto {self.pk}"


class EventProposition(models.Model):
    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name="structured_proposition")
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
    created_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_event_propositions")
    updated_by = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_event_propositions")
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
