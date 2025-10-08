from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from news.views import change_theme
from accounts import views as account_views

app_name = "bmx"

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
    path('login/', account_views.sign_in, name='login'),
    path('logout/', account_views.sign_out, name='logout'),
    path('signup/', account_views.sign_up, name='signup'),
    path('bmx-admin/', admin.site.urls),
    path('finance/', include('finance.urls'))
    ]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Czech BMX Website"
admin.site.index_title = "Management"