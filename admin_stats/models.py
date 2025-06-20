from django.db import models

class Visit(models.Model):
    ip_address = models.GenericIPAddressField()
    timestamp = models.DateTimeField(auto_now_add=True)
    user_agent = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    device_type = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return f"{self.ip_address} - {self.timestamp} - {self.user_agent} - {self.location}"