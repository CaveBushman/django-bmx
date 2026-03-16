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
