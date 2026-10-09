
from rest_framework import generics, filters
from rest_framework.permissions import AllowAny

from news.models import News
from news.serializer import NewsSerializer


from api.views._common import *  # noqa: F401,F403


class NewsListAPIView(generics.ListAPIView):
    queryset = News.objects.filter(published=True, publish_in_app=True).order_by("-publish_date", "-id")
    serializer_class = NewsSerializer
    permission_classes = [AllowAny]
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title"]
    ordering_fields = ["publish_date", "id"]
    ordering = ["-publish_date", "-id"]

__all__ = ['NewsListAPIView']
