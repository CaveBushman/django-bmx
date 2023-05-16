from django.shortcuts import render
from rest_framework import generics
# from rest_framework.views import APIView
from rider.models import Rider, ForeignRider
from event.models import Event, Entry
from news.models import News
from rider.serializers import RiderSerializer, ForeignRiderSerializer
from event.serializers import EventSerializer, EntrySerializer
from news.serializer import NewsSerializer
from django.contrib.auth.models import User
from rest_framework.permissions import IsAdminUser, IsAuthenticatedOrReadOnly

# Create your views here.


class RiderList(generics.ListAPIView):
    """API for list of all active BMX riders """
    queryset = Rider.objects.filter(is_active = True)
    serializer_class = RiderSerializer


class RiderDetail(generics.RetrieveAPIView):
    """API for riders detail"""
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer
    lookup_field = "uci_id"
    

class RiderNewAPIView(generics.CreateAPIView):
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer
    permission_classes = [IsAdminUser]


class RiderAdminAPIView(generics.RetrieveUpdateDestroyAPIView):
    """API for READ, PATCH, UPDATE, DELETE methods of riders object"""
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer
    lookup_field = "uci_id"
    permission_classes = [IsAdminUser]


class ForeignRiderList(generics.ListAPIView):
    """API for list of all foreign BMX riders """
    queryset = ForeignRider.objects.filter()
    serializer_class = ForeignRiderSerializer
    permission_classes = [IsAdminUser]



class ForeignRiderDetail(generics.RetrieveAPIView):
    """API for riders detail"""
    queryset = ForeignRider.objects.all()
    serializer_class = RiderSerializer
    lookup_field = "uci_id"
    permission_classes = [IsAdminUser]



class EventList(generics.ListAPIView):
    """API for list of all events"""
    queryset = Event.objects.all()
    serializer_class = EventSerializer


class EventDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAdminUser]


class NewsListAPIView(generics.ListAPIView):
    """API for list of all news"""
    queryset = News.objects.all()
    serializer_class = NewsSerializer


class EntryAdminAPIView(generics.RetrieveUpdateDestroyAPIView):
    """API for READ, PATCH, UPDATE, DELETE methods of riders object"""
    queryset = Entry.objects.all()
    serializer_class = EntrySerializer
    lookup_field = "transaction_id"