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
