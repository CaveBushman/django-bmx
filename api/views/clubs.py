
from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from club.models import Club
from club.serializers import ClubPublicSerializer


from api.views._common import *  # noqa: F401,F403


class ClubList(generics.ListAPIView):
    queryset = Club.objects.filter(is_active=True)
    serializer_class = ClubPublicSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["team_name"]
    ordering_fields = ["team_name"]
    ordering = ["team_name"]


class ClubDetail(generics.RetrieveAPIView):
    queryset = Club.objects.filter(is_active=True)
    serializer_class = ClubPublicSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

__all__ = ['ClubList', 'ClubDetail']
