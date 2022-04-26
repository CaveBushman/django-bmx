from django.urls import path
from . import views

app_name = 'rider'

urlpatterns = [

    path('', views.RidersListView, name='list'),
    path('<int:pk>', views.RiderDetailView, name='detail'),
    path('new', views.RiderNewView, name='new'),
    path('admin', views.RiderAdmin, name = "admin"),
    path('inactive', views.InactiveRidersViews, name="inactive"),
    path('licence', views.LicenceCheckViews, name='licence')

]
