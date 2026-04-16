from django.db import models

from event.models_events import Event
from rider.models import Rider


class Result(models.Model):
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True)
    date = models.DateField(null=True, blank=True)
    event_type = models.CharField(max_length=255, null=True, blank=True)
    organizer = models.CharField(max_length=100, null=True, blank=True)
    rider = models.ForeignKey(Rider, to_field="uci_id", db_constraint=False, on_delete=models.SET_NULL, null=True, blank=True)
    country = models.CharField(max_length=3, null=True, blank=True, default="CZE")
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    club = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    place = models.IntegerField(default=0)
    points = models.IntegerField(default=0)
    is_beginner = models.BooleanField(default=False)
    is_20 = models.BooleanField(default=True)
    marked_20 = models.BooleanField(default=0)
    marked_24 = models.BooleanField(default=0)

    class Meta:
        verbose_name = "Výsledek"
        verbose_name_plural = "Výsledky"

    def __str__(self):
        event_name = self.event.name if self.event else "Bez závodu"
        return f"{event_name} – {self.last_name} {self.first_name} ({self.category})"


class RaceRun(models.Model):
    result = models.ForeignKey(Result, on_delete=models.SET_NULL, related_name="runs", null=True, blank=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, null=True, blank=True)
    rider = models.ForeignKey(Rider, on_delete=models.SET_NULL, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    is_beginner = models.BooleanField(default=False)
    is_20 = models.BooleanField(null=True, blank=True)
    round_type = models.CharField(max_length=20)
    round_number = models.IntegerField(null=True, blank=True)
    heat_code = models.CharField(max_length=50, null=True, blank=True)
    plate = models.CharField(max_length=20, null=True, blank=True)
    gate = models.IntegerField(null=True, blank=True)
    lane = models.IntegerField(null=True, blank=True)
    place = models.CharField(max_length=10, null=True, blank=True)
    race_points = models.IntegerField(null=True, blank=True)
    moto_points = models.IntegerField(null=True, blank=True)
    qualified_to_next_round = models.BooleanField(null=True, blank=True)
    hill_time = models.FloatField(null=True, blank=True)
    finish_time = models.FloatField(null=True, blank=True)
    split_1 = models.FloatField(null=True, blank=True)
    split_2 = models.FloatField(null=True, blank=True)
    split_3 = models.FloatField(null=True, blank=True)
    split_4 = models.FloatField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Jízda závodníka"
        verbose_name_plural = "Jízdy závodníka"

    def __str__(self):
        label = self.result or self.rider or self.plate or "RaceRun"
        return f"{label} – {self.round_type} {self.round_number or ''} ({self.place})"
