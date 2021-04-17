from django.shortcuts import render
from rest_framework import generics
from rider.models import Rider
from event.models import Event
from rider.serializers import RiderSerializer
from event.serializers import EventSerializer
from django.contrib.auth.models import User
from rest_framework.permissions import IsAdminUser
# Create your views here.


class RiderList(generics.ListCreateAPIView):
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer
    permission_classes = [IsAdminUser]


class RiderDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer


class EventList(generics.ListCreateAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAdminUser]

class EventDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
