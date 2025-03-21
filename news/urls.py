from django.urls import path
from . import views

app_name = 'news'

urlpatterns = [

    path('', views.homepage_view, name='home'),
    path('news/', views.news_list_view, name='news-list'),
    path('news/<int:pk>', views.news_detail_view, name='news-detail'),
    path('rules/', views.rules_view, name='rules'),
    path('downloads', views.downloads_view, name='downloads')

]
