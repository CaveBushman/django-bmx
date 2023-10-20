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
    contact_phone = models.CharField(max_length=255, blank=True)

    bank_account = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)
    have_track = models.BooleanField(default=False)
    track_id = models.CharField(max_length=255, blank=True)
    mapy_cz_svg = models.CharField(max_length = 50000, null = True, blank=True) 
    lon = models.FloatField(default = 0, null=True, blank = True)
    lng = models.FloatField(default = 0, null=True, blank = True)

    created = models.DateTimeField(auto_now_add= True, blank=True, null=True)
    updated = models.DateTimeField(auto_now=True, blank=True, null=True)

    def __str__(self):
        return self.team_name


    def active_club():
        return Club.objects.filter(is_active=True).count()

    class Meta:
        verbose_name_plural = 'Kluby'
        ordering = ['team_name']
