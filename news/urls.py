from django.urls import path
from news.views import (
    homepage_view,
    news_list_view,
    news_detail_view,
    downloads_view,
    rules_view,
)

app_name = "news"

urlpatterns = [
    path("", homepage_view, name="homepage"),
    path("news/", news_list_view, name="news-list"),
    path("news/<int:pk>/", news_detail_view, name="news-detail"),
    path("downloads/", downloads_view, name="downloads"),
    path("rules/", rules_view, name="rules"),
]