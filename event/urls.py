from django.urls import path
from django.urls import re_path as url
from . import views

app_name = 'event'

urlpatterns = [
    path('', views.EventsListView, name='events'),
    path('<int:pk>', views.EventDetailViews, name='event-detail'),
    path('results/<int:pk>', views.ResultsView, name='results'),
    path('events-by-year/<int:pk>', views.EventsListByYearView, name='events-by-year'),
    path('entry/<int:pk>', views.EntryView, name='entry'),
    path('entry-rid/<int:pk>', views.EntryRidersView, name='entry-riders'),
    path('confirm', views.ConfirmView, name='confirm'),
    path('success/<int:pk>', views.SuccessView, name='success'),
    path('cancel', views.CancelView, name='cancel'),
    path('event-admin/<int:pk>', views.EventAdminView, name='event-admin'),
    path('find-payment', views.findPaymentView, name='find-payment'),
    path('ranking-table', views.RankingTableView, name='ranking-table')
]
