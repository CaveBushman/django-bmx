from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'rider'

urlpatterns = [

    path('', views.riders_list_view, name='list'),
    path('promo-codes', views.promo_codes_admin_view, name='promo-codes'),

    # 301 přesměrování ze starých /rider/ cest na nové /user/ cesty
    path('account', RedirectView.as_view(pattern_name='user:account', permanent=True), name='account'),
    path('mobile-app-subscription', RedirectView.as_view(pattern_name='user:subscription-mobile', permanent=True), name='mobile-app-subscription'),
    path('premium-subscriptions', RedirectView.as_view(pattern_name='user:subscriptions', permanent=True), name='premium-subscriptions'),
    path('redeem-promo', RedirectView.as_view(pattern_name='user:redeem', permanent=True), name='redeem-promo'),
    path('trainer-dashboard', RedirectView.as_view(pattern_name='user:trainer-dashboard', permanent=True), name='trainer-dashboard'),
    path('trainer-dashboard/club/<int:club_id>/export/riders/<str:export_format>', RedirectView.as_view(pattern_name='user:trainer-club-riders-export', permanent=True), name='trainer-club-riders-export'),
    path('trainer-dashboard/club/<int:club_id>/export/kpi/<str:export_format>', RedirectView.as_view(pattern_name='user:trainer-club-kpi-export', permanent=True), name='trainer-club-kpi-export'),
    path('<int:pk>/premium-stats', views.rider_premium_stats_view, name='premium-stats'),
    path('<int:pk>/premium-stats/export/pdf', views.rider_premium_stats_pdf_view, name='premium-stats-pdf'),
    path('<int:pk>/premium-stats/compare', views.rider_compare_view, name='premium-compare'),
    path('<int:pk>/premium-stats/subscribe', views.rider_premium_stats_subscribe_view, name='premium-stats-subscribe'),
    path('<int:pk>', views.rider_detail_view, name='detail'),
    path('new', views.rider_new_view, name='new'),
    path('new/licence-lookup', views.rider_licence_lookup_view, name='new-licence-lookup'),
    path('admin', views.rider_admin, name = "admin"),
    path('free-plates', views.free_plates_view, name='free-plates'),
    path('inactive', views.inactive_riders_views, name="inactive"),
    path('inactive/<int:rider_id>/deactivate', views.deactivate_inactive_rider_view, name='inactive-deactivate'),
    path('licence', views.licence_check_views, name='licence'),
    path('rank', views.ranking_count_views, name='ranking'),
    path('participation', views.participation_riders_on_event, name='participation'),
    path('participation-stats', views.participation_stats_view, name='participation-stats'),
    path('recalculate-riders-class', views.recalculate_riders_classes, name='recalculate-classes'),
    path('cruiser', views.calculate_cruiser_median, name='cruiser'),
    path('riders-by-class', views.riders_by_class_and_club, name='riders-by-class'),
    path('qualify', views.qualify_to_cn, name='qualify'),
    path('transponder-search', views.transponder_search_view, name='transponder-search'),
    path('plate-search', views.plate_search_view, name='plate-search'),

]
