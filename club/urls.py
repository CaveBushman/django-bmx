from django.urls import path
from . import views

app_name = 'club'

urlpatterns = [
    path('', views.ClubsListView, name = "clubs-list"),
    path('<int:pk>', views.ClubDetailView, name = 'club-detail'),
]
