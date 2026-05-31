from django.db import models

# Create your models here.


class Club(models.Model):
    """ Class for Club """

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

    created = models.DateTimeField(auto_now_add= True, blank=True, null=True)
    updated = models.DateTimeField(auto_now=True, blank=True, null=True)

    def __str__(self):
        return self.team_name


    @staticmethod
    def active_club():
        return Club.objects.filter(is_active=True).count()

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
