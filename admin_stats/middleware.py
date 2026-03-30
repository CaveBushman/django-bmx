import logging

from .models import Visit
from django.utils.deprecation import MiddlewareMixin


logger = logging.getLogger(__name__)


class VisitMiddleware(MiddlewareMixin):
    def process_request(self, request):
        ip = self.get_client_ip(request)
        if ip:
            try:
                Visit.objects.create(ip_address=ip)
            except Exception:
                logger.exception("Visit logging failed for ip=%s path=%s", ip, request.path)

    def get_client_ip(self, request):
        """ Získá IP adresu návštěvníka """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
