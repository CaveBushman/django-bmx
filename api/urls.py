from django.contrib import admin
from django.urls import include, path
from api import views
from rest_framework.urlpatterns import format_suffix_patterns

urlpatterns = [
    path('riders/', views.RiderListAPI.as_view()),
    path('riders/<int:pk>/', views.RiderDetailAPI.as_view()),
]

urlpatterns = format_suffix_patterns(urlpatterns)