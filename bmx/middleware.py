import uuid

from bmx.request_context import reset_request_id, set_request_id


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = set_request_id(request_id)
        request.request_id = request_id
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)

        response["X-Request-ID"] = request_id
        return response


class XRobotsTagMiddleware:
    """Přidá hlavičku ``X-Robots-Tag: noindex, nofollow`` na neindexovatelné cesty
    (média, API, admin, auth). Řeší GSC „Indexováno, ačkoli je přístup blokován
    souborem robots.txt" — na rozdíl od robots.txt (blokuje jen procházení)
    hlavička reálně vyřadí URL z indexu.

    Pozn.: v produkci servíruje /media/ obvykle nginx, ne Django — tam je potřeba
    stejnou hlavičku nastavit i v nginx (viz docs). Tady pokrývá cesty servírované
    Djangem/WhiteNoise."""

    NOINDEX_PREFIXES = ("/media/", "/api/", "/admin/", "/bmx-admin/",
                        "/accounts/login", "/accounts/register")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.NOINDEX_PREFIXES):
            response.setdefault("X-Robots-Tag", "noindex, nofollow")
        return response
