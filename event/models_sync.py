"""Záznamy o synchronizaci s centrální databází Event Control Admin.

Synchronizace je obousměrná: Event Control Admin si přes API čte jezdce a kluby
z webu (web je master dat) a web si naopak stahuje centrálně založené záznamy,
aby si k nim doplnil párovací ID a založil ty, které ještě nezná.
"""

from django.db import models


class EventControlSyncLog(models.Model):
    """Jeden běh synchronizace (jedna entita, jeden směr)."""

    class Direction(models.TextChoices):
        PULL = "pull", "Stažení z Event Control Admin"
        PUSH = "push", "Výdej pro Event Control Admin"

    class Entity(models.TextChoices):
        RIDERS = "riders", "Jezdci"
        CLUBS = "clubs", "Kluby"

    direction = models.CharField(max_length=10, choices=Direction.choices, default=Direction.PULL)
    entity = models.CharField(max_length=10, choices=Entity.choices)
    source = models.CharField(max_length=64, default="cron", help_text="cron / command / api")
    started = models.DateTimeField(auto_now_add=True)
    finished = models.DateTimeField(null=True, blank=True)
    succeeded = models.BooleanField(default=False)
    dry_run = models.BooleanField(default=False)

    received = models.IntegerField(default=0, help_text="Počet záznamů přijatých z centrální databáze")
    matched = models.IntegerField(default=0, help_text="Spárováno s existujícím záznamem")
    created = models.IntegerField(default=0, help_text="Založeno lokálně")
    skipped = models.IntegerField(default=0, help_text="Přeskočeno (nekompletní data)")
    conflicts = models.IntegerField(default=0, help_text="Spárováno, ale data se liší (web je master)")

    detail = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Synchronizace Event Control"
        verbose_name_plural = "Synchronizace Event Control"
        ordering = ["-started"]
        indexes = [
            models.Index(fields=["entity", "-started"], name="event_ecsync_entity_start"),
        ]

    def __str__(self):
        return f"{self.get_entity_display()} {self.get_direction_display()} {self.started:%d.%m.%Y %H:%M}"
