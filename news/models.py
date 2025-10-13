from email.policy import default
from django.db import models
from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save
from django.db.models import F
from ckeditor.fields import RichTextField
from accounts.models import Account
import datetime

# Create your models here.

class Tag(models.Model):
    caption=models.CharField(max_length=20)

    def __str__(self):
        return self.caption


class News (models.Model):
    """ Class for news on this website """

    title = models.CharField(max_length=255, default="")
    prefix = RichTextField(max_length=4000, default="", blank=True, null=True)
    content = RichTextField(max_length=10000, blank=True, null=True)
    tags = models.ManyToManyField(Tag)

    photo_01 = models.ImageField (upload_to = 'images/news', null=True, blank=True, default="images/news/AKBMX.jpg")
    photo_02 = models.ImageField (upload_to = 'images/news', null=True, blank=True)
    photo_03 = models.ImageField (upload_to = 'images/news', null=True, blank=True)

    time_to_read = models.IntegerField(default=0)

    view_count = models.PositiveIntegerField(default=0, db_index=True, help_text="Počet zhlédnutí")

    on_homepage = models.BooleanField(default=False)
    published = models.BooleanField(default=False)

    created_date = models.DateTimeField(editable=True, auto_now_add=True, null=True, blank=True)
    created = models.ForeignKey(Account, on_delete = models.SET_NULL, null=True, blank = True)

    publish_date = models.DateField(default=datetime.date.today)

    def __str__(self):
        return self.title

    def increment_views(self):
        # atomicky, bez race condition:
        News.objects.filter(pk=self.pk).update(view_count=F('view_count') + 1)
        self.refresh_from_db(fields=['view_count'])
    
    def sum_of_news():
        """ fukce vrací hodnotu všech zveřejněných článků """
        return News.objects.filter(published = True).count()

    class Meta:
        verbose_name = "Článek"
        verbose_name_plural = 'Články'

# nastavení time_to_read při ukládání článku
@receiver(pre_save, sender=News)
def set_time_to_read (sender, instance, *args, **kwargs):
    world_list = instance.content.split()
    number_of_words = len(world_list)
    time_to_read = int(number_of_words/200)
    if time_to_read < 1:
        time_to_read = 1
    instance.time_to_read = time_to_read   
pre_save.connect (set_time_to_read, sender = News)

# vymazání staré fotky z disku při její změně
@receiver(pre_save, sender=News)
def delete_photo_on_change_extension(sender, instance, *args, **kwargs):
    if instance.pk:
        try:
            old_photo_01 = News.objects.get(pk=instance.pk).photo_01
            old_photo_02 = News.objects.get(pk=instance.pk).photo_03
            old_photo_03 = News.objects.get(pk=instance.pk).photo_03
        except News.DoesNotExist:
            return
        else:
            new_photo_01 = instance.photo_01
            new_photo_02 = instance.photo_02
            new_photo_03 = instance.photo_03
            if old_photo_01 and old_photo_01.url != new_photo_01.url:
                old_photo_01.delete(save=False)
            if old_photo_02 and old_photo_02.url != new_photo_02.url:
                old_photo_02.delete(save=False)
            if old_photo_03 and old_photo_03.url != new_photo_03.url:
                old_photo_03.delete(save=False)
pre_save.connect(delete_photo_on_change_extension, sender=News)

class DocumentTag(models.Model):
    caption=models.CharField(max_length=20)

    def __str__(self):
        return self.caption
    
    class Meta:
        verbose_name = "Typ dokumentu"
        verbose_name_plural = 'Typ dokumentů'

class Downloads(models.Model):
    """ Model for downloads section """
    title = models.CharField(max_length=255)
    description = RichTextField(max_length=10000, blank=True, null=True)
    tags=models.ManyToManyField(DocumentTag)
    path = models.FileField(upload_to="documents", blank=True, null=True)
    published = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Ke stažení"
        verbose_name_plural = 'Ke stažení'