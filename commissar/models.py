from django.db import models

# Create your models here.


class Commissar (models.Model):

    LEVEL = (('UCI', 'UCI'), ('ENC', 'ENC'), ('Národní', 'Národní'))

    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)

    level = models.CharField(max_length=100, choices=LEVEL, default="Národní")

    class Meta:
        verbose_name = "Rozhodčí"
        verbose_name_plural = 'Rozhodčí'