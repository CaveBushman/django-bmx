from django.conf import settings
from django.db import models
from django.utils import timezone


class CommissionTask(models.Model):
    STATUS_NEW = "new"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_WAITING = "waiting"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"

    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"

    STATUS_CHOICES = (
        (STATUS_NEW, "Novy"),
        (STATUS_IN_PROGRESS, "Rozpracovano"),
        (STATUS_WAITING, "Ceka na reakci"),
        (STATUS_DONE, "Splneno"),
        (STATUS_CANCELLED, "Zruseno"),
    )

    PRIORITY_CHOICES = (
        (PRIORITY_LOW, "Nizka"),
        (PRIORITY_MEDIUM, "Stredni"),
        (PRIORITY_HIGH, "Vysoka"),
        (PRIORITY_URGENT, "Urgentni"),
    )

    title = models.CharField(max_length=200, verbose_name="Nazev ukolu")
    description = models.TextField(blank=True, verbose_name="Popis")
    event = models.ForeignKey(
        "event.Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commission_tasks",
        verbose_name="Souvisejici zavod",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_commission_tasks",
        verbose_name="Resitel",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_commission_tasks",
        verbose_name="Zadal",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        db_index=True,
        verbose_name="Stav",
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
        db_index=True,
        verbose_name="Priorita",
    )
    due_date = models.DateField(null=True, blank=True, db_index=True, verbose_name="Termin")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Splneno")
    created = models.DateTimeField(auto_now_add=True, null=True, verbose_name="Vytvoreno")
    updated = models.DateTimeField(auto_now=True, null=True, verbose_name="Upraveno")

    class Meta:
        verbose_name = "Ukol komise"
        verbose_name_plural = "Ukoly komise"
        ordering = ("due_date", "-created")

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status not in {self.STATUS_DONE, self.STATUS_CANCELLED}

    @property
    def is_overdue(self):
        return bool(self.due_date and self.is_open and self.due_date < timezone.localdate())

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_DONE and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status != self.STATUS_DONE:
            self.completed_at = None
        super().save(*args, **kwargs)
