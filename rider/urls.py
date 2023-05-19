from django.urls import path
from . import views

app_name = 'rider'

urlpatterns = [

    path('', views.riders_list_view, name='list'),
    path('<int:pk>', views.rider_detail_view, name='detail'),
    path('new', views.rider_new_view, name='new'),
    path('admin', views.rider_admin, name = "admin"),
    path('inactive', views.inactive_riders_views, name="inactive"),
    path('licence', views.licence_check_views, name='licence'),
    path('ranking', views.ranking_count_views, name='ranking'),

]
