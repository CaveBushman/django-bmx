from datetime import datetime
from .models import Visit
from django.utils.deprecation import MiddlewareMixin

class VisitMiddleware(MiddlewareMixin):
    def process_request(self, request):
        ip = self.get_client_ip(request)
        if ip:
            Visit.objects.create(ip_address=ip)
    
    def get_client_ip(self, request):
        """ Získá IP adresu návštěvníka """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip