"""Materializovaný aktuální ranking jezdců pro disciplíny 20\" a 24\".

Hodnoty jsou odvozené z výsledků. Zapisuje je ranking engine; běžná view je
nemají upravovat jako primární doménová data.
"""

from django.db import models
from rider.models import Rider

class Ranking(models.Model):

    """Poslední vypočtené body a pořadí jednoho jezdce."""

    rider = models.ForeignKey(Rider, on_delete=models.SET_NULL, null=True)
    point20 = models.IntegerField(default=0)
    point24 = models.IntegerField(default=0)

    ranking20 = models.IntegerField(default=0)
    ranking24 = models.IntegerField(default=0)
