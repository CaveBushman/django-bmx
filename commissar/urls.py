from django.urls import path
from . import views

app_name = 'commisar'

urlpatterns = [
    path('', views.list_of_commisars_view, name="commmisars-list"),

]