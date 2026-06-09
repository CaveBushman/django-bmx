import logging

from django.conf import settings
from django.db import OperationalError

from .models import Visit
from django.utils.deprecation import MiddlewareMixin


logger = logging.getLogger(__name__)

_IGNORED_EXTENSIONS = ('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.map', '.webp', '.avif', '.mp4', '.webm')
_IGNORED_PREFIXES = ('/static/', '/media/')

_geoip = None

def _get_geoip():
    global _geoip
    if _geoip is None:
        try:
            from django.contrib.gis.geoip2 import GeoIP2
            _geoip = GeoIP2()
        except Exception:
            _geoip = False
    return _geoip if _geoip else None


def _lookup_country(ip):
    try:
        g = _get_geoip()
        if g:
            return g.country_name(ip)
    except Exception:
        pass
    return None


class VisitMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if settings.DEBUG:
            return
        if request.path.startswith("/admin-stats/"):
            return
        if request.path.startswith("/csp-report/"):
            return
        if request.path.startswith(_IGNORED_PREFIXES):
            return
        if request.path.endswith(_IGNORED_EXTENSIONS):
            return

        ip = self.get_client_ip(request)
        if not ip:
            return

        ua = request.META.get('HTTP_USER_AGENT', '') or ''
        device_type = self._detect_device(ua)
        path = request.path[:500]
        location = _lookup_country(ip)

        try:
            Visit.objects.create(ip_address=ip, user_agent=ua[:512], device_type=device_type, path=path, location=location)
        except OperationalError:
            logger.warning("Visit logging skipped — db locked: ip=%s path=%s", ip, request.path)
        except Exception:
            try:
                Visit.objects.create(ip_address=ip)
            except Exception:
                logger.exception("Visit logging failed for ip=%s path=%s", ip, request.path)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    @staticmethod
    def _detect_device(ua):
        if not ua:
            return 'unknown'
        ua_lower = ua.lower()
        if any(k in ua_lower for k in ('ipad', 'tablet', 'kindle', 'playbook')):
            return 'tablet'
        if any(k in ua_lower for k in ('iphone', 'ipod', 'windows phone', 'blackberry')) or \
                ('android' in ua_lower and 'mobile' in ua_lower):
            return 'mobile'
        if any(k in ua_lower for k in ('mozilla', 'chrome', 'safari', 'firefox', 'edge', 'opera', 'trident')):
            return 'desktop'
        return 'unknown'
