from django.urls import path
from . import views

app_name = 'club'

urlpatterns = [
    path('', views.clubs_list_view, name="clubs-list"),
    path('<int:pk>', views.club_detail_view, name='club-detail'),
    path('participation/<int:pk>', views.participation_in_races, name="participation"),
    path('mapa-klubu/', views.mapa_klubu, name='mapa_klubu'),
]
