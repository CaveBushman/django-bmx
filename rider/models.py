from django.db import models
from club.models import Club
from django.contrib.auth.models import User

from datetime import date


# Create your models here.


class Rider(models.Model):
    """ Class for rider """

    CLASS_20 = (
    ('Boys 6', 'Boys 6'), ('Boys 7', 'Boys 7'), ('Boys 8', 'Boys 8'), ('Boys 9', 'Boys 9'), ('Boys 10', 'Boys 10'),
    ('Boys 11', 'Boys 11'), ('Boys 12', 'Boys 12'), ('Boys 13', 'Boys 13'), ('Boys 14', 'Boys 14'),
    ('Boys 15', 'Boys 15'), ('Boys 16', 'Boys 16'), ('Men 17-24', 'Men 17-24'), ('Men 25-29', 'Men 25-29'),
    ('Men 30-34', 'Men 30-34'), ('Men 35 and over', 'Men 35 and over'), ('Girls 7', 'Girls 7'),
    ('Girls 8', 'Girls 8'), ('Girls 9', 'Girls 9'), ('Girls 10', 'Girls 10'), ('Girls 11', 'Girls 11'),
    ('Girls 12', 'Girls 12'), ('Girls 13', 'Girls 13'), ('Girls 14', 'Girls 14'), ('Girls 15', 'Girls 16'),
    ('Women 17-24', 'Women 17-24'), ('Women 25 and over', 'Women 25 and over'), ('Men Junior', 'Men Junior'),
    ('Men Under 23', 'Men Under 23'), ('Men Elite', 'Men Elite'), ('Women Junior', 'Women Junior'),
    ('Women Under 23', 'Women Under 23'), ('Women Elite', 'Women Elite'))
    CLASS_24 = (
    ('Boys 12 and under', 'Boys 12 and under'), ('Boys 13 and 14', 'Boys 13 and 14'), ('Boys 15 a 16', 'Boys 15 a 16'),
    ('Men 17-24', 'Men 17-24'), ('Men 25-29', 'Men 25-39'), ('Men 30-34', 'Men 30-34'), ('Men 35-39', 'Men 35-39'),
    ('Men 40-49',
     'Men 40-49'), ('Men 50 and over', 'Men 50 and over'), ('Girls 12 and under', 'Girls 12 and under'),
    ('Girls 13-16', 'Girls 13-16'), ('Women 17-29', 'Women 17-29'), ('Women 30-39', 'Women 30-99'),
    ('Women 40 and over', 'Women 40 and over'))

    GENDER = (('Muž', 'Muž'), ('Žena', 'Žena'), ('Ostatní', 'Ostatní'))

    uci_id = models.IntegerField(unique=True)
    first_name = models.CharField(max_length=255, blank=False)
    middle_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=False)

    date_of_birth = models.DateField(blank=False)
    gender = models.CharField(choices=GENDER, max_length=10)
    have_girl_bonus = models.BooleanField(default=False)

    email = models.EmailField(max_length=100, null=True, blank=True)

    photo = models.ImageField(
        upload_to='static/images/riders/', blank=True, null=True, default='static/images/riders/uni.jpeg')

    club = models.ForeignKey(
        Club, related_name='rider_club', null=True, on_delete=models.SET_NULL)

    is_20 = models.BooleanField(default=False)
    is_24 = models.BooleanField(default=False)
    is_elite = models.BooleanField(default=False)

    points_20 = models.IntegerField(default=0)
    points_24 = models.IntegerField(default=0)

    ranking_20 = models.CharField(max_length=10, null=True, blank=True)
    ranking_24 = models.CharField(max_length=10, null=True, blank=True)

    is_in_talent_team = models.BooleanField(default=False)
    is_in_representation = models.BooleanField(default=False)

    class_20 = models.CharField(
        max_length=50, choices=CLASS_20, default="Boys 6", null=True)
    class_24 = models.CharField(
        max_length=50, choices=CLASS_24, default="Boys 12 and under", null=True)

    transponder_20 = models.CharField(max_length=8, blank=True, null=True)
    transponder_24 = models.CharField(max_length=8, blank=True, null=True)

    plate = models.IntegerField(blank=True, null=True, default=0)
    plate_color_20 = models.CharField(max_length=10, default="yellow", null=True)

    emergency_contact = models.CharField(max_length=255, blank=True, null=True)
    emergency_phone = models.CharField(max_length=255, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_approwe = models.BooleanField(default=False)
    have_valid_licence = models.BooleanField(default=True)

    created = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.first_name + ' ' + self.last_name

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name_plural = 'Jezdci'

    def get_age(self):
        return date.today().year - self.date_of_birth.year

    def set_class_20(self):
        age = self.get_age()

        if self.is_elite:
            if self.gender == "Muž" or self.gender == "Ostatní":
                if age <= 18:
                    self.class_20 = "Men Junior"
                    self.plate_color_20 = "black"
                elif age <= 22:
                    self.class_20 = "Men Under 23"
                    self.plate_color_20 = "white"
                else:
                    self.class_20 = "Men Elite"
                    self.plate_color_20 = "white"
            else:
                if age <= 18:
                    self.class_20 = "Women Junior"
                    self.plate_color_20 = "black"
                elif age <= 22:
                    self.class_20 = "Women Under 23"
                    self.plate_color_20 = "white"
                else:
                    self.class_20 = "Women Elite"
                    self.plate_color_20 = "white"

        if not self.is_elite:
            if self.gender == "Muž" or self.gender == "Ostatní":
                if age <= 6:
                    self.class_20 = "Boys 6"
                    self.plate_color_20 = "yellow"
                elif age == 7:
                    self.class_20 = "Boys 7"
                    self.plate_color_20 = "yellow"
                elif age == 8:
                    self.class_20 = "Boys 8"
                    self.plate_color_20 = "yellow"
                elif age == 9:
                    self.class_20 = "Boys 9"
                    self.plate_color_20 = "yellow"
                elif age == 10:
                    self.class_20 = "Boys 10"
                    self.plate_color_20 = "yellow"
                elif age == 11:
                    self.class_20 = "Boys 11"
                    self.plate_color_20 = "yellow"
                elif age == 12:
                    self.class_20 = "Boys 12"
                    self.plate_color_20 = "yellow"
                elif age == 13:
                    self.class_20 = "Boys 13"
                    self.plate_color_20 = "yellow"
                elif age == 14:
                    self.class_20 = "Boys 14"
                    self.plate_color_20 = "yellow"
                elif age == 15:
                    self.class_20 = "Boys 15"
                    self.plate_color_20 = "yellow"
                elif age == 16:
                    self.class_20 = "Boys 16"
                    self.plate_color_20 = "yellow"
                elif age <= 24:
                    self.class_20 = "Men 17-24"
                    self.plate_color_20 = "yellow"
                elif age <= 29:
                    self.class_20 = "Men 25-29"
                    self.plate_color_20 = "yellow"
                elif age <= 34:
                    self.class_20 = "Men 30-34"
                    self.plate_color_20 = "yellow"
                else:
                    self.class_20 = "Men 35 and over"
                    self.plate_color_20 = "yellow"
            else:
                if age <= 6:
                    self.class_20 = "Girls 6"
                    self.plate_color_20 = "blue"
                elif age == 7:
                    self.class_20 = "Girls 7"
                    self.plate_color_20 = "blue"
                elif age == 8:
                    self.class_20 = "Girls 8"
                    self.plate_color_20 = "blue"
                elif age == 9:
                    self.class_20 = "Girls 9"
                    self.plate_color_20 = "blue"
                elif age == 10:
                    self.class_20 = "Girls 10"
                    self.plate_color_20 = "blue"
                elif age == 11:
                    self.class_20 = "Girls 11"
                    self.plate_color_20 = "blue"
                elif age == 12:
                    self.class_20 = "Girls 12"
                    self.plate_color_20 = "blue"
                elif age == 13:
                    self.class_20 = "Girls 13"
                    self.plate_color_20 = "blue"
                elif age == 14:
                    self.class_20 = "Girls 14"
                    self.plate_color_20 = "blue"
                elif age == 15:
                    self.class_20 = "Girls 15"
                    self.plate_color_20 = "blue"
                elif age == 16:
                    self.class_20 = "Girls 16"
                    self.plate_color_20 = "blue"
                elif age <= 24:
                    self.class_20 = "Women 17-24"
                    self.plate_color_20 = "blue"
                else:
                    self.class_20 = "Women 25 and over"
                    self.plate_color_20 = "blue"
        self.save()

    def set_class_24(self):
        age = self.get_age()
        if self.gender == "Muž" or self.gender == "Ostatní":
            if age <= 12:
                self.class_24 = "Boys 12 and under"
            elif age <= 14:
                self.class_24 = "Boys 13 and 14"
            elif age <= 16:
                self.class_24 = "Boys 15 and 16"
            elif age <= 24:
                self.class_24 = "Men 17-24"
            elif age <= 29:
                self.class_24 = "Men 25-29"
            elif age <= 34:
                self.class_24 = "Men 30-34"
            elif age <= 39:
                self.class_24 = "Men 35-39"
            elif age <= 49:
                self.class_24 = "Men 40-49"
            else:
                self.class_24 = "Men 50 and over"
        else:
            if age <= 12:
                self.class_24 = "Girls 12 and under"
            elif age <= 16:
                self.class_24 = "Girls 13-16"
            elif age <= 29:
                self.class_24 = "Women 17-29"
            elif age <= 39:
                self.class_24 = "Women 30-39"
            else:
                self.class_24 = "Women 40 and over"
        self.save()
