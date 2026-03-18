from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Sponsor(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=120, verbose_name="Název")
    alt_text = models.CharField(max_length=160, verbose_name="Alt text")
    logo_light = models.ImageField(upload_to="images/sponsors/", verbose_name="Logo pro light režim")
    logo_dark = models.ImageField(
        upload_to="images/sponsors/",
        blank=True,
        null=True,
        verbose_name="Logo pro dark režim",
    )
    url = models.URLField(blank=True, verbose_name="Odkaz")
    valid_from = models.DateField(verbose_name="Platí od")
    valid_to = models.DateField(blank=True, null=True, verbose_name="Platí do")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Pořadí")
    is_published = models.BooleanField(default=True, verbose_name="Publikováno")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Sponzor"
        verbose_name_plural = "Sponzoři"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError({"valid_to": "Datum 'Platí do' musí být stejné nebo pozdější než 'Platí od'."})

    @property
    def dark_logo_or_light(self):
        return self.logo_dark or self.logo_light
