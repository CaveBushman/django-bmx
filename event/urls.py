from django.urls import path
from . import views

app_name = 'event'

urlpatterns = [
    path('', views.events_list_view, name='events'),
    path('<int:pk>', views.event_detail_views, name='event-detail'),
    path('results/<int:pk>', views.results_view, name='results'),
    path('events-by-year/<int:pk>', views.events_list_by_year_view, name='events-by-year'),
    path('entry/<int:pk>', views.entry_view, name='entry'),
    path('entry-rid/<int:pk>', views.entry_riders_view, name='entry-riders'),
    path('confirm', views.confirm_view, name='confirm'),
    path('success/<int:pk>', views.success_view, name='success'),
    path('cancel', views.cancel_view, name='cancel'),
    path('event-admin/<int:pk>', views.event_admin_view, name='event-admin'),
    path('find-payment', views.find_payment_view, name='find-payment'),
    path('ranking-table', views.ranking_table_view, name='ranking-table'),
    path('entry-foreign/<int:pk>', views.entry_foreign_view, name='entry-foreign'),
    path('ec_by_club_xls/<int:pk>', views.ec_by_club_xls, name='ec_by_club_xls'),
    path('summary_riders_in_event/<int:pk>', views.summary_riders_in_event, name='%% end')
]
