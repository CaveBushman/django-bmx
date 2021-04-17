from django.contrib import admin
from django.urls import include, path
from api import views
from rest_framework.urlpatterns import format_suffix_patterns

urlpatterns = [
    path('riders/', views.RiderList.as_view()),
    path('riders/<int:pk>/', views.RiderDetail.as_view()),
    path('events/', views.EventList.as_view()),
    path('events/<int:pk>/', views.EventDetail.as_view()),
]

urlpatterns = format_suffix_patterns(urlpatterns)
