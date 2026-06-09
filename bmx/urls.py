from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from accounts import views as account_views
from bmx import views as bmx_views
from api.views import FcmTokenAPIView

app_name = "bmx"
handler400 = "bmx.views.error_400_view"
handler403 = "bmx.views.error_403_view"
handler404 = "bmx.views.error_404_view"
handler500 = "bmx.views.error_500_view"

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("ckeditor5/", include("django_ckeditor_5.urls")),
    path('api/', include('api.urls')),             # primární namespace "api" — existující klienti
    path('api/v1/', include(('api.urls', 'api_v1'))),  # v1 namespace — nové mobilní klienty
    path('', include('news.urls')),
    path('accounts/', include('accounts.urls')),
    path('event/', include('event.urls')),
    path('rider/', include('rider.urls')),
    path('user/', include('rider.user_urls')),
    path('club/', include('club.urls')),
    path('ranking/', include('ranking.urls')),
    path('api-auth/', include('rest_framework.urls')),
    path('admin-stats/', include('admin_stats.urls')),
    path('todo/', include('todo.urls')),
    path('login/', account_views.sign_in, name='login'),
    path('logout/', account_views.sign_out, name='logout'),
    path('signup/', account_views.sign_up, name='signup'),
    path('bmx-admin/', admin.site.urls),
    path('finance/', include('finance.urls')),
    path('eshop/', include('eshop.urls')),
    # Alias pro mobilní aplikaci — Flutter app volá /user/notification-tokens/
    path('user/notification-tokens/', FcmTokenAPIView.as_view(), name='fcm-token-mobile'),
    path('healthz', bmx_views.healthz_view, name='healthz'),
    path('readyz', bmx_views.readyz_view, name='readyz'),
    path('csp-report/', bmx_views.csp_report_view, name='csp-report'),
    path('detailxmlk.xml', bmx_views.legacy_sitemap_redirect_view, name='legacy-sitemap'),
    path('sitemap.xml', bmx_views.sitemap_view, name='sitemap'),
    ]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Czech BMX Website"
admin.site.index_title = "Management"
