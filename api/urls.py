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
    path("auth/avatar-request/", views.AvatarRequestAPIView.as_view(), name="avatar-request"),
    path("auth/register/", views.RegisterAPIView.as_view(), name="register"),
    path("auth/activation/resend/", views.ActivationResendAPIView.as_view(), name="activation-resend"),
    path("auth/password/reset/", views.PasswordResetRequestAPIView.as_view(), name="password-reset"),
    path("auth/password/reset/confirm/", views.PasswordResetConfirmAPIView.as_view(), name="password-reset-confirm"),
    path("credit/topup/", views.CreditTopUpAPIView.as_view(), name="credit-topup"),

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
    path("events/<int:pk>/", views.EventPublicDetailAPIView.as_view(), name="event-detail"),
    path("events/<int:pk>/admin/", views.EventDetail.as_view(), name="event-detail-admin"),
    path("events/<int:pk>/entry-info/", views.EventEntryInfoAPIView.as_view(), name="event-entry-info"),
    path("events/<int:pk>/enter/", views.EventEnterAPIView.as_view(), name="event-enter"),

    # News
    path("news/", views.NewsListAPIView.as_view(), name="news-list"),

    # Entries — moje přihlášky + storno
    path("entries/my/", views.MyEntriesAPIView.as_view(), name="my-entries"),
    path("entries/<int:pk>/cancel/", views.EntryCancelAPIView.as_view(), name="entry-cancel"),

    # Foreign rider entries
    path("events/<int:pk>/foreign-entry-info/", views.ForeignEventEntryInfoAPIView.as_view(), name="foreign-entry-info"),
    path("events/<int:pk>/foreign-enter/", views.ForeignEventEnterAPIView.as_view(), name="foreign-enter"),
    path("entries/foreign/<int:pk>/cancel/", views.ForeignEntryCancelAPIView.as_view(), name="foreign-entry-cancel"),

    # Entries (admin)
    path("entry/<str:transaction_id>/", views.EntryAdminAPIView.as_view(), name="entry-admin"),

    # E-shop — catalogue
    path("eshop/categories/", views.EshopCategoryListAPIView.as_view(), name="eshop-category-list"),
    path("eshop/products/", views.EshopProductListAPIView.as_view(), name="eshop-product-list"),
    path("eshop/products/<slug:slug>/", views.EshopProductDetailAPIView.as_view(), name="eshop-product-detail"),

    # E-shop — cart (session-based)
    path("eshop/cart/", views.EshopCartAPIView.as_view(), name="eshop-cart"),
    path("eshop/cart/<int:variant_id>/", views.EshopCartItemAPIView.as_view(), name="eshop-cart-item"),

    # E-shop — checkout & orders
    path("eshop/checkout/", views.EshopCheckoutAPIView.as_view(), name="eshop-checkout"),
    path("eshop/orders/", views.EshopOrderListAPIView.as_view(), name="eshop-order-list"),
    path("eshop/orders/<int:pk>/", views.EshopOrderDetailAPIView.as_view(), name="eshop-order-detail"),
    path("eshop/orders/<int:pk>/cancel/", views.EshopOrderCancelAPIView.as_view(), name="eshop-order-cancel"),

    # Ranking
    path("ranking/categories/", views.RankingCategoryListAPIView.as_view(), name="ranking-category-list"),
    path("ranking/", views.RankingAPIView.as_view(), name="ranking"),

    # OpenAPI schema + Swagger UI
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("schema/swagger/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="swagger"),
]
