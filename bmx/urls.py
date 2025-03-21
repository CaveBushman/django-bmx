"""bmx URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from django.views.generic import TemplateView
from django.views.static import serve
from django.urls import re_path as url
from news.views import change_theme

urlpatterns = [
    path('api/', include('api.urls')),
    path('', include('news.urls')),
    path('change/', change_theme, name='change'),
    path('accounts/', include('accounts.urls')),
    path('event/', include('event.urls')),
    path('rider/', include('rider.urls')),
    path('club/', include('club.urls')),
    path('ranking/', include('ranking.urls')),
    path('api-auth/', include('rest_framework.urls')),
    path('admin-stats/', include('admin_stats.urls')),
    path('', include("django.contrib.auth.urls")),
    path('bmx-admin/', admin.site.urls),
    path("__reload__/", include("django_browser_reload.urls")),
    ]
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Czech BMX Website"
admin.site.index_title = "Management"