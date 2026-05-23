from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from api import views

app_name = "api"

urlpatterns = [
    # Auth
    path("auth/login/", views.LoginAPIView.as_view(), name="login"),
    path("auth/logout/", views.LogoutAPIView.as_view(), name="logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", views.MeAPIView.as_view(), name="me"),
    path("auth/password/change/", views.PasswordChangeAPIView.as_view(), name="password-change"),

    # Riders
    path("riders/", views.RiderList.as_view(), name="rider-list"),
    path("riders/<int:uci_id>/", views.RiderDetail.as_view(), name="rider-detail"),
    path("riders/new/", views.RiderNewAPIView.as_view(), name="rider-new"),
    path("riders/admin/<int:uci_id>/", views.RiderAdminAPIView.as_view(), name="rider-admin"),

    # Foreign riders
    path("foreignriders/", views.ForeignRiderList.as_view(), name="foreignrider-list"),
    path("foreignriders/<int:uci_id>/", views.ForeignRiderDetail.as_view(), name="foreignrider-detail"),

    # Clubs
    path("clubs/", views.ClubList.as_view(), name="club-list"),

    # Events
    path("events/", views.EventList.as_view(), name="event-list"),
    path("events/<int:pk>/", views.EventDetail.as_view(), name="event-detail"),

    # News
    path("news/", views.NewsListAPIView.as_view(), name="news-list"),

    # Entries (admin)
    path("entry/<str:transaction_id>/", views.EntryAdminAPIView.as_view(), name="entry-admin"),

    # OpenAPI schema + Swagger UI
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("schema/swagger/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="swagger"),
]
