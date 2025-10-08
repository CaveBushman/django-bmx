from django.urls import path
from . import views

app_name = 'eshop'

urlpatterns = [
    path('eshop', views.finance_admin, name='eshop' )
    ]