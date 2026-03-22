from django.urls import path
from . import views

app_name = 'rider'

urlpatterns = [

    path('', views.riders_list_view, name='list'),
    path('trainer-dashboard', views.trainer_dashboard_view, name='trainer-dashboard'),
    path('trainer-dashboard/club/<int:club_id>/export/riders/<str:export_format>', views.trainer_club_riders_export_view, name='trainer-club-riders-export'),
    path('trainer-dashboard/club/<int:club_id>/export/kpi/<str:export_format>', views.trainer_club_kpi_export_view, name='trainer-club-kpi-export'),
    path('account', views.account_settings_invoices_view, name='account'),
    path('premium-subscriptions', views.rider_premium_subscriptions_view, name='premium-subscriptions'),
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
    path('recalculate-riders-class', views.recalculate_riders_classes, name='recalculate-classes'),
    path('cruiser', views.calculate_cruiser_median, name='cruiser'),
    path('riders-by-class', views.riders_by_class_and_club, name='riders-by-class'),
    path('qualify', views.qualify_to_cn, name='qualify'),
    path('transponder-search', views.transponder_search_view, name='transponder-search'),
    path('plate-search', views.plate_search_view, name='plate-search'),

]
