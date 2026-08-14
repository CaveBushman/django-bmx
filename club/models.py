"""Kluby a klubová družstva pro MČR.

``Club`` je sdílená organizační entita pro jezdce, účty, závody a fakturaci.
Mazání nebo slučování klubů proto vyžaduje kontrolu všech těchto vazeb.
"""

import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Club(models.Model):
    """Organizace sdružující jezdce a pořádající závody."""

    REGION = (('hlavní město Praha', 'hlavní město Praha'), ('Středočeský kraj', 'Středočeský kraj'), ('Jihočeský kraj', 'Jihočeský kraj'), ('Plzeňský kraj', 'Plzeňský kraj'), ('Ústecký kraj', 'Ústecký kraj'), ('Liberecký kraj', 'Liberecký kraj'),
              ('Královéhradecký kraj', 'Královéhradecký kraj'), ('Pardubický kraj', 'Pardubický kraj'), ('Kraj Vysočina', 'Kraj Vysočina'), ('Jihomoravský kraj', 'Jihomoravský kraj'), ('Olomoucký kraj', 'Olomoucký kraj'), ('Zlínský kraj', 'Zlínský kraj'), ('Moravskoslezský kraj', 'Moravskoslezský kraj'))

    team_name = models.CharField(max_length=255, blank=False, default="")
    club_name = models.CharField(max_length=255, blank=True, null=True)
    ico = models.CharField(max_length=8, blank=True)

    street = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    region = models.CharField(
        max_length=50, choices=REGION, default='hlavní město Praha')

    web = models.URLField(max_length=255, blank=True)
    facebook = models.URLField(max_length=255, blank=True)
    instagram = models.URLField(max_length=255, blank=True)

    contact_person = models.CharField(max_length=255, blank=True)
    contact_email = models.CharField(max_length=255, blank=True)
    billing_email = models.EmailField(max_length=255, blank=True)
    contact_phone = models.CharField(max_length=255, blank=True)

    bank_account = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)
    have_track = models.BooleanField(default=False)
    opening_hours = models.TextField(blank=True, default='')
    track_id = models.CharField(max_length=255, blank=True)
    mapy_cz_svg = models.CharField(max_length = 50000, null = True, blank=True) 
    lon = models.FloatField(default = 0, null=True, blank = True)
    lng = models.FloatField(default = 0, null=True, blank = True)

    riders_on_events = models.FileField(upload_to='riders_in_events/', null=True, blank=True)

    # Přístupové údaje organizace pro BMX Event Control (server + username + password).
    # Heslo je uložené jen jako hash, plaintext se zobrazí pouze jednou při vygenerování.
    event_control_enabled = models.BooleanField(
        "BMX Event Control – přístup povolen",
        default=False,
        help_text="Povoluje stahování přihlášených jezdců přes API pro závody tohoto pořadatele.",
    )
    event_control_username = models.CharField(
        "BMX Event Control – username",
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        default=None,
    )
    event_control_password = models.CharField(
        "BMX Event Control – hash hesla",
        max_length=128,
        blank=True,
        default="",
        editable=False,
    )
    event_control_password_updated = models.DateTimeField(
        "BMX Event Control – heslo změněno",
        null=True,
        blank=True,
        editable=False,
    )
    event_control_last_access = models.DateTimeField(
        "BMX Event Control – poslední přístup",
        null=True,
        blank=True,
        editable=False,
    )
    # Párování s centrální databází klubů v Event Control Admin (web zůstává master dat).
    event_control_id = models.CharField(
        "ID v Event Control Admin",
        max_length=64,
        blank=True,
        default="",
        db_index=True,
    )
    event_control_synced = models.DateTimeField(
        "Naposledy synchronizováno s Event Control Admin",
        null=True,
        blank=True,
    )

    created = models.DateTimeField(auto_now_add= True, blank=True, null=True)
    updated = models.DateTimeField(auto_now=True, blank=True, null=True)

    def __str__(self):
        return self.team_name

    def save(self, *args, **kwargs):
        # Prázdný username musí být NULL, jinak by druhý klub bez údajů porušil unique.
        if not self.event_control_username:
            self.event_control_username = None
        super().save(*args, **kwargs)

    @staticmethod
    def active_club():
        return Club.objects.filter(is_active=True).count()

    # -- BMX Event Control ---------------------------------------------------

    def _build_event_control_username(self):
        """Navrhne username ve tvaru ``ec-<klub>``, unikátní v rámci klubů."""
        base = slugify(self.team_name or f"club-{self.pk}")[:40] or f"club-{self.pk}"
        candidate = f"ec-{base}"
        suffix = 2
        while Club.objects.filter(event_control_username=candidate).exclude(pk=self.pk).exists():
            candidate = f"ec-{base}-{suffix}"
            suffix += 1
        return candidate

    def set_event_control_password(self, raw_password):
        self.event_control_password = make_password(raw_password)
        self.event_control_password_updated = timezone.now()

    def check_event_control_password(self, raw_password) -> bool:
        if not self.event_control_password or not raw_password:
            return False
        return check_password(raw_password, self.event_control_password)

    def generate_event_control_credentials(self) -> str:
        """Vygeneruje (a uloží) username i nové heslo. Vrací heslo v plaintextu.

        Plaintext se nikde neukládá — zobrazí se jednou tomu, kdo údaje generuje,
        a zadá se do nastavení organizace v BMX Event Control.
        """
        if not self.event_control_username:
            self.event_control_username = self._build_event_control_username()
        raw_password = secrets.token_urlsafe(24)
        self.set_event_control_password(raw_password)
        self.event_control_enabled = True
        self.save(
            update_fields=[
                "event_control_username",
                "event_control_password",
                "event_control_password_updated",
                "event_control_enabled",
                "updated",
            ]
        )
        return raw_password

    def revoke_event_control_credentials(self):
        """Zneplatní heslo a vypne přístup; username zůstává pro dohledatelnost."""
        self.event_control_password = ""
        self.event_control_password_updated = None
        self.event_control_enabled = False
        self.save(
            update_fields=[
                "event_control_password",
                "event_control_password_updated",
                "event_control_enabled",
                "updated",
            ]
        )

    class Meta:
        verbose_name_plural = 'Kluby'
        ordering = ['team_name']


class McrClubTeam(models.Model):
    year = models.PositiveSmallIntegerField()
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="mcr_teams")
    name = models.CharField(max_length=120)
    manager_name = models.CharField(max_length=120)
    created_by = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_mcr_club_teams",
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["year", "club__team_name", "name"]
        verbose_name = "Družstvo MČR klubů"
        verbose_name_plural = "Družstva MČR klubů"
        constraints = [
            models.UniqueConstraint(fields=["year", "club", "name"], name="unique_mcr_club_team_name")
        ]

    def __str__(self):
        return f"{self.year} - {self.club} - {self.name}"


class McrClubTeamMember(models.Model):
    WHEEL_20 = "20"
    WHEEL_24 = "24"
    WHEEL_CHOICES = (
        (WHEEL_20, '20"'),
        (WHEEL_24, '24"'),
    )

    team = models.ForeignKey(McrClubTeam, on_delete=models.CASCADE, related_name="members")
    rider = models.ForeignKey("rider.Rider", on_delete=models.CASCADE, related_name="mcr_club_team_memberships")
    wheel = models.CharField(max_length=2, choices=WHEEL_CHOICES)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Člen družstva MČR klubů"
        verbose_name_plural = "Členové družstva MČR klubů"
        constraints = [
            models.UniqueConstraint(fields=["team", "rider", "wheel"], name="unique_mcr_club_team_member_wheel")
        ]

    def __str__(self):
        return f'{self.rider} {self.wheel}"'
