from django.db import models
from club.models import Club
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from datetime import date
import re


# Create your models here.


class Rider(models.Model):
    """ Class for rider """

    CLASS_20 = (
    ('Boys 6', 'Boys 6'), ('Boys 7', 'Boys 7'), ('Boys 8', 'Boys 8'), ('Boys 9', 'Boys 9'), ('Boys 10', 'Boys 10'),
    ('Boys 11', 'Boys 11'), ('Boys 12', 'Boys 12'), ('Boys 13', 'Boys 13'), ('Boys 14', 'Boys 14'),
    ('Boys 15', 'Boys 15'), ('Boys 16', 'Boys 16'), ('Men 17-24', 'Men 17-24'), ('Men 25-29', 'Men 25-29'),
    ('Men 30-34', 'Men 30-34'), ('Men 35 and over', 'Men 35 and over'), ('Girls 7', 'Girls 7'),
    ('Girls 8', 'Girls 8'), ('Girls 9', 'Girls 9'), ('Girls 10', 'Girls 10'), ('Girls 11', 'Girls 11'),
    ('Girls 12', 'Girls 12'), ('Girls 13', 'Girls 13'), ('Girls 14', 'Girls 14'), ('Girls 15', 'Girls 15'),('Girls 16', 'Girls 16'),
    ('Women 17-24', 'Women 17-24'), ('Women 25 and over', 'Women 25 and over'), ('Men Junior', 'Men Junior'),
    ('Men Under 23', 'Men Under 23'), ('Men Elite', 'Men Elite'), ('Women Junior', 'Women Junior'),
    ('Women Under 23', 'Women Under 23'), ('Women Elite', 'Women Elite'))
    CLASS_24 = (
    ('Boys 12 and under', 'Boys 12 and under'), ('Boys 13 and 14', 'Boys 13 and 14'), ('Boys 15 and 16', 'Boys 15 and 16'),
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
    rc = models.CharField(max_length=1000, blank=True, null=True, default="")
    gender = models.CharField(choices=GENDER, max_length=10)
    have_girl_bonus = models.BooleanField(default=False)

    email = models.EmailField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=100, null=True, blank=True)

    street = models.CharField(max_length=1000, blank=True, null=True, default="")
    city = models.CharField(max_length=1000, blank=True, null=True, default="")
    zip=models.CharField(max_length=1000, blank=True, null=True, default="")

    photo = models.ImageField(
        upload_to='images/riders/', blank=True, null=True, default='images/riders/uni.jpeg')

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
    two_years_inactive = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True, null=True)
    updated = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.first_name + ' ' + self.last_name

    class Meta:
        db_table = 'Jezdci'
        ordering = ['last_name', 'first_name']
        verbose_name = "Jezdec"
        verbose_name_plural = 'Jezdci'

    def get_age(self, rider):
        return date.today().year - rider.date_of_birth.year
    
    def sum_of_riders():
        return Rider.objects.filter(is_active=True).count

    @staticmethod
    def set_class_20(gender, age : int, is_elite):
        if is_elite:
            if gender == "Muž" or gender == "Ostatní":
                if age <= 18:
                    return "Men Junior"
                elif age <= 22:
                    return "Men Under 23"
                else:
                    return "Men Elite"
            else:
                if age <= 18:
                    return "Women Junior"
                elif age <= 22:
                    return "Women Under 23"
                else:
                    return "Women Elite"

        if not is_elite:
            if gender == "Muž" or gender == "Ostatní":
                if age <= 6:
                    return "Boys 6"
                elif age == 7:
                    return "Boys 7"
                elif age == 8:
                    return "Boys 8"
                elif age == 9:
                    return "Boys 9"
                elif age == 10:
                    return "Boys 10"
                elif age == 11:
                    return "Boys 11"
                elif age == 12:
                    return "Boys 12"
                elif age == 13:
                    return "Boys 13"
                elif age == 14:
                    return "Boys 14"
                elif age == 15:
                    return "Boys 15"
                elif age == 16:
                    return "Boys 16"
                elif age <= 24:
                    return "Men 17-24"
                elif age <= 29:
                    return "Men 25-29"
                elif age <= 34:
                    return "Men 30-34"
                else:
                    return "Men 35 and over"

            else:
                if age <= 7:
                    return "Girls 7"
                elif age == 8:
                    return "Girls 8"
                elif age == 9:
                    return "Girls 9"
                elif age == 10:
                    return "Girls 10"
                elif age == 11:
                    return "Girls 11"
                elif age == 12:
                    return "Girls 12"
                elif age == 13:
                    return "Girls 13"
                elif age == 14:
                    return "Girls 14"
                elif age == 15:
                    return "Girls 15"
                elif age == 16:
                    return "Girls 16"
                elif age <= 24:
                    return "Women 17-24"
                else:
                    return "Women 25 and over"

    @staticmethod
    def set_class_24(gender, age:int):
        if gender == "Muž" or gender == "Ostatní":
            if age <= 12:
                return "Boys 12 and under"
            elif age <= 14:
                return "Boys 13 and 14"
            elif age <= 16:
                return "Boys 15 and 16"
            elif age <= 24:
                return "Men 17-24"
            elif age <= 29:
                return "Men 25-29"
            elif age <= 34:
                return "Men 30-34"
            elif age <= 39:
                return "Men 35-39"
            elif age <= 49:
                return "Men 40-49"
            else:
                return "Men 50 and over"
        else:
            if age <= 12:
                return "Girls 12 and under"
            elif age <= 16:
                return "Girls 13-16"
            elif age <= 29:
                return "Women 17-29"
            elif age <= 39:
                return "Women 30-39"
            else:
                return "Women 40 and over"

    @staticmethod
    def plate_color(class_20):
        if re.search("Elite", class_20):
            return "white"
        elif re.search("Under", class_20):
            return "gray"
        elif re.search("Junior", class_20):
            return "black"
        elif re.search("Girls", class_20) or re.search("Women", class_20):
            return "blue"
        else:
            return "yellow"

# nastavení kategorie jezdce při ukládání
@receiver(pre_save, sender=Rider)
def set_class(sender, instance, **kwargs):
    age = instance.get_age(instance)
    is_elite = instance.is_elite
    instance.class_20 = instance.set_class_20(instance.gender, age, is_elite)
    instance.class_24 = instance.set_class_24(instance.gender, age)
    instance.plate_color_20 = instance.plate_color(instance.class_20)
pre_save.connect (set_class, sender = Rider)

# vymazání staré fotky jezdce při její změně
@receiver(pre_save, sender=Rider)
def delete_file_on_change_extension(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_photo = Rider.objects.get(pk=instance.pk).photo
        except Rider.DoesNotExist:
            return
        else:
            new_photo = instance.photo
            if old_photo == "static/images/riders/uni.jpeg":
                return
            if old_photo and old_photo.url != new_photo.url:
                old_photo.delete(save=False)
pre_save.connect(delete_file_on_change_extension, sender=Rider)

class ForeignRider(models.Model):
    """ Class for foreign rider """

    CLASS_20 = (
    ('Boys 6', 'Boys 6'), ('Boys 7', 'Boys 7'), ('Boys 8', 'Boys 8'), ('Boys 9', 'Boys 9'), ('Boys 10', 'Boys 10'),
    ('Boys 11', 'Boys 11'), ('Boys 12', 'Boys 12'), ('Boys 13', 'Boys 13'), ('Boys 14', 'Boys 14'),
    ('Boys 15', 'Boys 15'), ('Boys 16', 'Boys 16'), ('Men 17-24', 'Men 17-24'), ('Men 25-29', 'Men 25-29'),
    ('Men 30-34', 'Men 30-34'), ('Men 35 and over', 'Men 35 and over'), ('Girls 7', 'Girls 7'),
    ('Girls 8', 'Girls 8'), ('Girls 9', 'Girls 9'), ('Girls 10', 'Girls 10'), ('Girls 11', 'Girls 11'),
    ('Girls 12', 'Girls 12'), ('Girls 13', 'Girls 13'), ('Girls 14', 'Girls 14'), ('Girls 15', 'Girls 15'),('Girls 16', 'Girls 16'),
    ('Women 17-24', 'Women 17-24'), ('Women 25 and over', 'Women 25 and over'), ('Men Junior', 'Men Junior'),
    ('Men Under 23', 'Men Under 23'), ('Men Elite', 'Men Elite'), ('Women Junior', 'Women Junior'),
    ('Women Under 23', 'Women Under 23'), ('Women Elite', 'Women Elite'))
    CLASS_24 = (
    ('Boys 12 and under', 'Boys 12 and under'), ('Boys 13 and 14', 'Boys 13 and 14'), ('Boys 15 and 16', 'Boys 15 and 16'),
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

    class_20 = models.CharField(
        max_length=50, choices=CLASS_20, default="Boys 6", null=True)
    class_24 = models.CharField(
        max_length=50, choices=CLASS_24, default="Boys 12 and under", null=True)
    
    is_20 = models.BooleanField(default=False)
    is_24 = models.BooleanField(default=False)
    is_elite = models.BooleanField(default=False)

    transponder_20 = models.CharField(max_length=8, blank=True, null=True)
    transponder_24 = models.CharField(max_length=8, blank=True, null=True)

    plate = models.IntegerField(blank=True, null=True, default=0)

    state = models.CharField(max_length=3, null=True, blank=True)
    club = models.CharField(max_length=200, null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True, null=True)
    updated = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.first_name + ' ' + self.last_name

    class Meta:
        db_table = 'Zahranicni_jezdci'
        ordering = ['last_name', 'first_name']
        verbose_name = "Zahranicni jezdec"
        verbose_name_plural = 'Zahranicni jezdci'

    def get_age(self, rider):
        return date.today().year - rider.date_of_birth.year

    @staticmethod
    def set_class_20(gender, age : int, is_elite):
        if is_elite:
            if gender == "Muž" or gender == "Ostatní":
                if age <= 18:
                    return "Men Junior"
                elif age <= 22:
                    return "Men Under 23"
                else:
                    return "Men Elite"
            else:
                if age <= 18:
                    return "Women Junior"
                elif age <= 22:
                    return "Women Under 23"
                else:
                    return "Women Elite"

        if not is_elite:
            if gender == "Muž" or gender == "Ostatní":
                if age <= 6:
                    return "Boys 6"
                elif age == 7:
                    return "Boys 7"
                elif age == 8:
                    return "Boys 8"
                elif age == 9:
                    return "Boys 9"
                elif age == 10:
                    return "Boys 10"
                elif age == 11:
                    return "Boys 11"
                elif age == 12:
                    return "Boys 12"
                elif age == 13:
                    return "Boys 13"
                elif age == 14:
                    return "Boys 14"
                elif age == 15:
                    return "Boys 15"
                elif age == 16:
                    return "Boys 16"
                elif age <= 24:
                    return "Men 17-24"
                elif age <= 29:
                    return "Men 25-29"
                elif age <= 34:
                    return "Men 30-34"
                else:
                    return "Men 35 and over"

            else:
                if age <= 7:
                    return "Girls 7"
                elif age == 8:
                    return "Girls 8"
                elif age == 9:
                    return "Girls 9"
                elif age == 10:
                    return "Girls 10"
                elif age == 11:
                    return "Girls 11"
                elif age == 12:
                    return "Girls 12"
                elif age == 13:
                    return "Girls 13"
                elif age == 14:
                    return "Girls 14"
                elif age == 15:
                    return "Girls 15"
                elif age == 16:
                    return "Girls 16"
                elif age <= 24:
                    return "Women 17-24"
                else:
                    return "Women 25 and over"

    @staticmethod
    def set_class_24(gender, age:int):
        if gender == "Muž" or gender == "Ostatní":
            if age <= 12:
                return "Boys 12 and under"
            elif age <= 14:
                return "Boys 13 and 14"
            elif age <= 16:
                return "Boys 15 and 16"
            elif age <= 24:
                return "Men 17-24"
            elif age <= 29:
                return "Men 25-29"
            elif age <= 34:
                return "Men 30-34"
            elif age <= 39:
                return "Men 35-39"
            elif age <= 49:
                return "Men 40-49"
            else:
                return "Men 50 and over"
        else:
            if age <= 12:
                return "Girls 12 and under"
            elif age <= 16:
                return "Girls 13-16"
            elif age <= 29:
                return "Women 17-29"
            elif age <= 39:
                return "Women 30-39"
            else:
                return "Women 40 and over"

@receiver(pre_save, sender=ForeignRider)
def set_class_foreign(sender, instance, *args, **kwargs):
    age = instance.get_age(instance)
    is_elite = instance.is_elite
    instance.class_20 = instance.set_class_20(instance.gender, age, is_elite)
    instance.class_24 = instance.set_class_24(instance.gender, age)
pre_save.connect (set_class_foreign, sender = ForeignRider)

