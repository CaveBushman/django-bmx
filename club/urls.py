from django.urls import path
from . import views

app_name = 'club'

urlpatterns = [
    path('', views.clubs_list_view, name="clubs-list"),
    path('mcr-druzstva/', views.mcr_club_teams_redirect_view, name='mcr-club-teams-current'),
    path('mcr-druzstva/<int:year>/', views.mcr_club_teams_view, name='mcr-club-teams'),
    path('<int:pk>', views.club_detail_view, name='club-detail'),
    path('<int:pk>/riders-on-events-export', views.riders_on_events_export_view, name='riders-on-events-export'),
    path('participation/<int:pk>', views.participation_in_races, name="participation"),
    path('mapa-klubu/', views.mapa_klubu, name='mapa_klubu'),
]
