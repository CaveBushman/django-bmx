from django.db import models
from ckeditor.fields import RichTextField
from accounts.models import Account
import datetime

# Create your models here.

class News (models.Model):

    FOCUS = (('Závody', 'Závody'), ('Reprezentace', 'Reprezentace'), ('Administrativa', 'Administrativa'), ('Ostatní', 'Ostatní'))

    title = models.CharField(max_length=255, default="")

    content = RichTextField(max_length=10000, blank=True, null=True)

    focus = models.CharField(choices=FOCUS, max_length=255, default='Ostatní')

    photo_01 = models.ImageField (upload_to = 'static/images/news', null=True, blank=True)
    photo_02 = models.ImageField (upload_to = 'static/images/news', null=True, blank=True)
    photo_03 = models.ImageField (upload_to = 'static/images/news', null=True, blank=True)

    on_homepage = models.BooleanField(default=False)
    published = models.BooleanField(default=False)

    created_date = models.DateTimeField(editable=True, auto_now_add=True, null=True, blank=True)
    created = models.ForeignKey(Account, on_delete = models.SET_NULL, null=True, blank = True)

    publish_date = models.DateField(default=datetime.date.today)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name_plural = 'Články'
