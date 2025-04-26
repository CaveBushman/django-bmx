from django.db import models
from rider.models import Rider

# Create your models here.

class Ranking(models.Model):

    rider = models.ForeignKey(Rider, on_delete=models.SET_NULL, null=True)
    point20 = models.IntegerField(default=0)
    point24 = models.IntegerField(default=0)

    ranking20 = models.IntegerField(default=0)
    ranking24 = models.IntegerField(default=0)

