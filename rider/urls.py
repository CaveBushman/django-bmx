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
    path('participation', views.participation_riders_on_event, name='participation'),
    path('recalculate-riders-class', views.recalculate_riders_classes, name='recalculate-classes'),
    path('cruiser', views.calculate_cruiser_median, name='cruiser'),
    path('riders-by-class', views.riders_by_class_and_club, name='riders-by-class'),
    path('qualify', views.qualify_to_cn, name='qualify')

]
