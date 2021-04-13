from django.urls import path
from . import views

app_name = 'rider'

urlpatterns = [

    path('', views.RidersListView, name='riders-list'),
    path('<int:pk>', views.RiderDetailView, name='rider-detail'),
    path('new', views.RiderNewView, name='rider-new'),

]
