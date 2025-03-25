from dotenv import load_dotenv
import os

load_dotenv()

from django.conf import settings
from django.shortcuts import render
from django.contrib.auth.models import User
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticatedOrReadOnly, AllowAny
import openai
from rider.models import Rider, ForeignRider
from event.models import Event, Entry
from news.models import News
from rider.serializers import RiderSerializer, ForeignRiderSerializer
from event.serializers import EventSerializer, EntrySerializer
from news.serializer import NewsSerializer

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
    permission_classes = [IsAdminUser]


class ChatbotAPIView(APIView):
    """Jednoduchý chatbot endpoint s fallbackem na OpenAI"""
    permission_classes = [AllowAny]

    def post(self, request):
        user_message = request.data.get("message", "").lower().strip()

        # Pevně dané odpovědi
        faq = {
            "kdy je další závod": "Další závod se koná 12. dubna v Pardubicích.",
            "kdy se otevře registrace": "Registrace se otevře 1. dubna.",
            "kolik stojí startovné": "Startovné závisí na kategorii, většinou 400–600 Kč."
        }

        if user_message in faq:
            answer = faq[user_message]
        else:
            openai.api_key = os.getenv("OPENAI_API_KEY")
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": user_message}]
            )
            answer = response.choices[0].message.content.strip()

        return Response({"reply": answer})