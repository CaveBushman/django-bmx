import logging

from django.conf import settings
from django.db import OperationalError

from .models import Visit
from django.utils.deprecation import MiddlewareMixin


logger = logging.getLogger(__name__)


class VisitMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if settings.DEBUG or request.path.startswith("/csp-report/"):
            return

        ip = self.get_client_ip(request)
        if ip:
            try:
                Visit.objects.create(ip_address=ip)
            except OperationalError:
                logger.warning("Visit logging skipped because database is locked for ip=%s path=%s", ip, request.path)
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
