from django.db import models
from event.models import Event
from club.models import Club


class EventInvoice(models.Model):
    """ Třída pro vystavení faktur za startovné, samostatná řada mimo e-shop """
    number = models.CharField(max_length=255, unique=True)
    issue_date = models.DateField()
    due_date = models.DateField()
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    club = models.ForeignKey(Club, on_delete=models.CASCADE)

    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    word = models.FileField(upload_to="invoices/word/", blank=True, null=True)
    pdf = models.FileField(upload_to="invoices/pdf/", blank=True, null=True)
    xml_export = models.FileField(upload_to="invoices/xml/", blank=True, null=True)
    email_sent_at = models.DateTimeField(blank=True, null=True)
    email_sent_to = models.EmailField(max_length=255, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Faktura {self.number}"

    class Meta:
        verbose_name = "Faktura za startovné"
        verbose_name_plural = 'Faktury za startovné'
        constraints = [
            models.UniqueConstraint(fields=["event", "club"], name="finance_invoice_event_club_unique"),
        ]


class EventInvoiceOverride(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="invoice_overrides")
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="invoice_overrides")
    manual_descriptions = models.TextField(blank=True)
    manual_amounts = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ruční úprava položek faktury"
        verbose_name_plural = "Ruční úpravy položek faktur"
        constraints = [
            models.UniqueConstraint(fields=["event", "club"], name="finance_invoice_override_event_club_unique"),
        ]


class EventCashReceipt(models.Model):
    number = models.CharField(max_length=255, unique=True)
    issue_date = models.DateField()
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="cash_receipts")

    customer_name = models.CharField(max_length=255, blank=True)
    customer_street = models.CharField(max_length=255, blank=True)
    customer_city = models.CharField(max_length=255, blank=True)
    customer_zip_code = models.CharField(max_length=32, blank=True)
    customer_country = models.CharField(max_length=255, blank=True)
    rider_name = models.CharField(max_length=255)
    uci_id = models.CharField(max_length=64, blank=True)
    category = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    pdf = models.FileField(upload_to="cash-receipts/pdf/", blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Pokladní doklad {self.number}"

    class Meta:
        verbose_name = "Pokladní doklad"
        verbose_name_plural = "Pokladní doklady"
        ordering = ["-issue_date", "-created"]
