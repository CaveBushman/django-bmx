from django.db import models

class Visit(models.Model):
    ip_address = models.GenericIPAddressField()
    timestamp = models.DateTimeField(auto_now_add=True)
    user_agent = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    device_type = models.CharField(max_length=50, blank=True, null=True)
    path = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["timestamp"], name="admin_visit_timestamp"),
            models.Index(fields=["ip_address", "timestamp"], name="admin_visit_ip_timestamp"),
        ]

    def __str__(self):
        return f"{self.ip_address} - {self.timestamp} - {self.path}"
