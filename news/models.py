from django.db import models
from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save
from ckeditor.fields import RichTextField
from accounts.models import Account
import datetime

# Create your models here.

class Tag(models.Model):
    caption=models.CharField(max_length=20)

    def __str__(self):
        return self.caption


class News (models.Model):
    """ Class for news on this wabsite """

    title = models.CharField(max_length=255, default="")
    content = RichTextField(max_length=10000, blank=True, null=True)
    tags = models.ManyToManyField(Tag)

    photo_01 = models.ImageField (upload_to = 'static/images/news', null=True, blank=True)
    photo_02 = models.ImageField (upload_to = 'static/images/news', null=True, blank=True)
    photo_03 = models.ImageField (upload_to = 'static/images/news', null=True, blank=True)

    time_to_read = models.IntegerField(default=0)

    on_homepage = models.BooleanField(default=False)
    published = models.BooleanField(default=False)

    created_date = models.DateTimeField(editable=True, auto_now_add=True, null=True, blank=True)
    created = models.ForeignKey(Account, on_delete = models.SET_NULL, null=True, blank = True)

    publish_date = models.DateField(default=datetime.date.today)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name_plural = 'Články'
    
    def sum_of_news():
        return News.objects.filter(published = True).count()

@receiver(pre_save, sender=News)
def set_time_to_read (sender, instance, *args, **kwargs):
    world_list = instance.content.split()
    number_of_words = len(world_list)
    time_to_read = int(number_of_words/200)
    if time_to_read < 1:
        time_to_read = 1
    instance.time_to_read = time_to_read
    
pre_save.connect (set_time_to_read, sender = News)