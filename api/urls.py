from django.contrib import admin
from django.urls import include, path
from api import views
from rest_framework.urlpatterns import format_suffix_patterns

urlpatterns = [
    path('riders', views.RiderList.as_view()),
    path('riders/<int:uci_id>', views.RiderDetail.as_view()),
    path('riders/new', views.RiderNewAPIView.as_view()),
    path('riders/admin/<int:uci_id>', views.RiderAdminAPIView.as_view()),

    path('foreignriders', views.ForeignRiderList.as_view()),
    path('foreignriders/<int:uci_id>', views.ForeignRiderDetail.as_view()),

    path('events', views.EventList.as_view()),
    path('events/<int:pk>', views.EventDetail.as_view()),

    path('news', views.NewsListAPIView.as_view()),

    path('entry', views.EntryAdminAPIView.as_view()),
]

urlpatterns = format_suffix_patterns(urlpatterns)
