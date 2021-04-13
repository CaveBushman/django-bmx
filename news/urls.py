from django.urls import path
from . import views

app_name = 'news'

urlpatterns = [

    path('', views.HomepageView, name='home'),
    path('news/', views.NewsListView, name='news-list'),
    path('news/<int:pk>', views.NewsDetailView, name='news-detail'),
    path('rules/', views.RulesView, name='rules'),

]
