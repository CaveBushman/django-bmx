import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from bmx.health import collect_readiness_checks
from bmx.rate_limit import get_rate_limit_subject, is_rate_limited
from club.models import Club
from event.models import Event
from news.models import News
from rider.models import Rider


logger = logging.getLogger("security.csp")


@csrf_exempt
def csp_report_view(request):
    """Přijme CSP report-only hlášení z prohlížeče a zaloguje ho."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    raw_body = request.body
    max_body_bytes = getattr(settings, "CSP_REPORT_MAX_BODY_BYTES", 16 * 1024)
    if len(raw_body) > max_body_bytes:
        logger.warning(
            "CSP report dropped because body is too large",
            extra={
                "content_type": request.headers.get("Content-Type", ""),
                "body_size": len(raw_body),
                "remote_addr": request.META.get("REMOTE_ADDR", ""),
            },
        )
        return HttpResponse(status=204)

    limited, _attempts = is_rate_limited(
        "csp-report",
        get_rate_limit_subject(request),
        window_seconds=getattr(settings, "CSP_REPORT_RATE_LIMIT_WINDOW_SECONDS", 60),
        max_attempts=getattr(settings, "CSP_REPORT_RATE_LIMIT_MAX_ATTEMPTS", 120),
    )
    if limited:
        logger.warning(
            "CSP report dropped because rate limit was exceeded",
            extra={"remote_addr": request.META.get("REMOTE_ADDR", "")},
        )
        return HttpResponse(status=204)

    body = raw_body.decode("utf-8", errors="replace")
    content_type = request.headers.get("Content-Type", "")

    try:
        report = json.loads(body) if body else {}
    except json.JSONDecodeError:
        logger.warning(
            "CSP report with invalid JSON",
            extra={"content_type": content_type, "body_preview": body[:2000]},
        )
        return HttpResponse(status=204)

    logger.info(
        "CSP report received",
        extra={
            "content_type": content_type,
            "csp_report": report,
            "user_agent": request.headers.get("User-Agent", ""),
            "referer": request.headers.get("Referer", ""),
            "remote_addr": request.META.get("REMOTE_ADDR", ""),
        },
    )
    return HttpResponse(status=204)


def error_404_view(request, exception):
    """Projektová 404 stránka s korektním HTTP statusem."""
    return render(request, "404.html", status=404)


def healthz_view(request):
    return JsonResponse({"status": "ok"})


def readyz_view(request):
    payload = collect_readiness_checks()
    status_code = 200 if payload["status"] == "ok" else 503
    return JsonResponse(payload, status=status_code)


def sitemap_view(request):
    """Dynamicky generuje sitemap.xml s URL adresami."""
    try:
        cache_key = f"sitemap:xml:{request.get_host()}"
        cached_xml = cache.get(cache_key)
        if cached_xml is not None:
            return HttpResponse(cached_xml, content_type="application/xml")

        urls = []

        static_urls = [
            (reverse("news:homepage"), "weekly", "1.0"),
            (reverse("news:news-list"), "daily", "0.9"),
            (reverse("event:events"), "daily", "0.9"),
            (reverse("club:clubs-list"), "weekly", "0.8"),
            (reverse("rider:list"), "weekly", "0.7"),
            (reverse("news:downloads"), "weekly", "0.6"),
            (reverse("news:rules"), "monthly", "0.6"),
        ]
        today_iso = timezone.now().date().isoformat()

        for path, freq, priority in static_urls:
            urls.append(
                {
                    "loc": request.build_absolute_uri(path),
                    "lastmod": today_iso,
                    "changefreq": freq,
                    "priority": priority,
                }
            )

        for news in News.objects.filter(published=True).only("id", "slug", "publish_date"):
            urls.append(
                {
                    "loc": request.build_absolute_uri(news.get_absolute_url()),
                    "lastmod": news.publish_date.isoformat() if news.publish_date else today_iso,
                    "changefreq": "monthly",
                    "priority": "0.8",
                }
            )

        for event in Event.objects.filter(canceled=False).only("id", "updated"):
            urls.append(
                {
                    "loc": request.build_absolute_uri(reverse("event:event-detail", kwargs={"pk": event.pk})),
                    "lastmod": event.updated.isoformat() if event.updated else today_iso,
                    "changefreq": "weekly",
                    "priority": "0.8",
                }
            )

        for club in Club.objects.filter(is_active=True).only("id", "updated"):
            urls.append(
                {
                    "loc": request.build_absolute_uri(reverse("club:club-detail", kwargs={"pk": club.pk})),
                    "lastmod": club.updated.isoformat() if club.updated else today_iso,
                    "changefreq": "monthly",
                    "priority": "0.7",
                }
            )

        for rider in Rider.objects.filter(is_active=True, is_approved=True).only("id", "created"):
            urls.append(
                {
                    "loc": request.build_absolute_uri(reverse("rider:detail", kwargs={"pk": rider.pk})),
                    "lastmod": rider.created.date().isoformat() if rider.created else today_iso,
                    "changefreq": "monthly",
                    "priority": "0.5",
                }
            )

        # Generuj XML
        xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

        for url in urls:
            xml_lines.append("  <url>")
            xml_lines.append(f"    <loc>{url['loc']}</loc>")
            xml_lines.append(f"    <lastmod>{url['lastmod']}</lastmod>")
            xml_lines.append(f"    <changefreq>{url['changefreq']}</changefreq>")
            xml_lines.append(f"    <priority>{url['priority']}</priority>")
            xml_lines.append("  </url>")

        xml_lines.append("</urlset>")

        xml_content = "\n".join(xml_lines)
        cache.set(cache_key, xml_content, settings.SITEMAP_CACHE_SECONDS)
        return HttpResponse(xml_content, content_type="application/xml")
    except Exception as e:
        logger.error(f"Chyba při generování sitemapů: {e}")
        return HttpResponse(
            '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>',
            content_type="application/xml",
            status=500
        )
