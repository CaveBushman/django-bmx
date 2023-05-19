from django.urls import path
from . import views

app_name = 'club'

urlpatterns = [
    path('', views.clubs_list_view, name="clubs-list"),
    path('<int:pk>', views.club_detail_view, name='club-detail'),
]
