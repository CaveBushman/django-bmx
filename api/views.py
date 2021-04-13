from django.shortcuts import render
from rest_framework import generics
from rider.models import Rider
from rider.serializers import RiderSerializer
# Create your views here.


class RiderListAPI(generics.ListAPIView):
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer


class RiderDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer