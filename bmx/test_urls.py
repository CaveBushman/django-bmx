from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import path
from django.views.decorators.csrf import csrf_protect

from bmx.urls import urlpatterns as project_urlpatterns


@csrf_protect
def csrf_protected_view(request):
    return HttpResponse("csrf-ok")


def permission_denied_view(request):
    raise PermissionDenied("forbidden in test")


def runtime_error_view(request):
    raise RuntimeError("boom")


handler400 = "bmx.views.error_400_view"
handler403 = "bmx.views.error_403_view"
handler404 = "bmx.views.error_404_view"
handler500 = "bmx.views.error_500_view"


urlpatterns = [
    path("__test__/csrf-protected/", csrf_protected_view, name="test-csrf-protected"),
    path("__test__/permission-denied/", permission_denied_view, name="test-permission-denied"),
    path("__test__/runtime-error/", runtime_error_view, name="test-runtime-error"),
] + project_urlpatterns
