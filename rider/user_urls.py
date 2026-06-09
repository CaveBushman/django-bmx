from django.urls import path
from . import views

app_name = "user"

urlpatterns = [
    path("account", views.account_settings_invoices_view, name="account"),
    path("subscription/mobile", views.mobile_app_subscription_view, name="subscription-mobile"),
    path("subscriptions", views.rider_premium_subscriptions_view, name="subscriptions"),
    path("redeem", views.redeem_promo_code_view, name="redeem"),
    path("trainer-dashboard", views.trainer_dashboard_view, name="trainer-dashboard"),
    path("trainer-dashboard/club/<int:club_id>/export/riders/<str:export_format>", views.trainer_club_riders_export_view, name="trainer-club-riders-export"),
    path("trainer-dashboard/club/<int:club_id>/export/kpi/<str:export_format>", views.trainer_club_kpi_export_view, name="trainer-club-kpi-export"),
]
