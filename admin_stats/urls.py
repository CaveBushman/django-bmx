from django.urls import path
from .views import visit_stats

app_name = 'admin_stats'

urlpatterns = [
    path('', visit_stats, name='visit_stats'),
]