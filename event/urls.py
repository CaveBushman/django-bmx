from django.urls import path
from . import views

app_name = 'event'

urlpatterns = [

    path('', views.EventsListView, name='events'),
    path('<int:pk>', views.EventDetailViews, name='event-detail'),
    path('upload-results/<int:pk>', views.UploadResultViews, name='upload-result'),
    path('results/<int:pk>', views.ResultsView, name='results'),
    path('events-by-year/<int:pk>', views.EventsListByYearView, name='events-by-year'),
    path('entry/<int:pk>', views.EntryView, name='entry'),
    path('confirm', views.ConfirmView, name='confirm'),
    path('success', views.SuccessView, name='success'),
    path('cancel', views.CancelView, name='cancel'),
    path('event-admin/<int:pk>', views.EventAdminView, name='event-admin')

]
