from django.db import models
from event.models import Event
from club.models import Club
# Create your models here.
class EventInvoice(models.Model):
    """ Třída pro vystavení faktur za startovné, samostatná řada mimo e-shop """
    number = models.CharField(max_length=255, unique=True)
    issue_date = models.DateField()
    due_date = models.DateField()
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    club = models.ForeignKey(Club, on_delete=models.CASCADE)

    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    word = models.FileField(upload_to="invoices/word/")
    pdf = models.FileField(upload_to="invoices/pdf/", blank=True, null=True)

    def __str__(self):
        return f"Faktura {self.number}"

    class Meta:
        verbose_name = "Faktura za startovné"
        verbose_name_plural = 'Faktury za startovné'