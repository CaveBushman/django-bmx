import json
import logging

from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt


logger = logging.getLogger("security.csp")


@csrf_exempt
def csp_report_view(request):
    """Přijme CSP report-only hlášení z prohlížeče a zaloguje ho."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    body = request.body.decode("utf-8", errors="replace")
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


def sitemap_view(request):
    """Dynamicky generuje sitemap.xml s URL adresami."""
    try:
        urls = []

        # Statické stránky
        static_urls = [
            ("", "weekly"),  # Homepage
            ("news/", "weekly"),
            ("events/", "weekly"),
            ("clubs/", "weekly"),
            ("riders/", "monthly"),
        ]

        for path, freq in static_urls:
            urls.append({
                "loc": request.build_absolute_uri(reverse("home") if path == "" else f"/{path}"),
                "lastmod": datetime.now().isoformat(),
                "changefreq": freq,
                "priority": "0.8" if path == "" else "0.7"
            })

        # Dynamické stránky - zprávy
        for news in News.objects.all():
            urls.append({
                "loc": request.build_absolute_uri(f"/news/{news.id}/"),
                "lastmod": news.updated.isoformat() if hasattr(news, 'updated') else datetime.now().isoformat(),
                "changefreq": "monthly",
                "priority": "0.6"
            })

        # Dynamické stránky - závody
        for event in Event.objects.all():
            urls.append({
                "loc": request.build_absolute_uri(f"/events/{event.id}/"),
                "lastmod": event.modified.isoformat() if hasattr(event, 'modified') else datetime.now().isoformat(),
                "changefreq": "weekly",
                "priority": "0.7"
            })

        # Dynamické stránky - kluby
        for club in Clubs.objects.all():
            urls.append({
                "loc": request.build_absolute_uri(f"/clubs/{club.id}/"),
                "lastmod": datetime.now().isoformat(),
                "changefreq": "monthly",
                "priority": "0.6"
            })

        # Dynamické stránky - jezdci
        for rider in Rider.objects.all():
            urls.append({
                "loc": request.build_absolute_uri(f"/riders/{rider.id}/"),
                "lastmod": datetime.now().isoformat(),
                "changefreq": "monthly",
                "priority": "0.5"
            })

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

        return HttpResponse(
            "\n".join(xml_lines),
            content_type="application/xml"
        )
    except Exception as e:
        logger.error(f"Chyba při generování sitemapů: {e}")
        return HttpResponse(
            '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>',
            content_type="application/xml",
            status=500
        )
