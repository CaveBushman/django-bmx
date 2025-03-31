from dotenv import load_dotenv
import os
from django.db import models
from chat.models import ChatLog
from django.conf import settings
from django.shortcuts import render
from django.contrib.auth.models import User
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticatedOrReadOnly, AllowAny
import requests
import re
from rider.models import Rider, ForeignRider
from event.models import Event, Entry
from news.models import News
from club.models import Club
from rider.serializers import RiderSerializer, ForeignRiderSerializer
from event.serializers import EventSerializer, EntrySerializer
from news.serializer import NewsSerializer
from club.serializers import ClubSerializer
import logging


load_dotenv()
settings.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


# Create your views here.

logger = logging.getLogger(__name__)

class RiderList(generics.ListAPIView):
    """API for list of all active BMX riders """
    queryset = Rider.objects.filter(is_active=True)
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

class ClubList(generics.ListAPIView):
    queryset = Club.objects.all()
    serializer_class = ClubSerializer


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
        try:
            user_message = request.data.get("message", "").strip()

            # Pevně dané odpovědi
            faq = {
                "kdy je další závod": "Podívej se na tomto webu do sekce Kalendář.",
                "kdy se otevře registrace": "Registrace se otevře 1. dubna.",
                "kolik stojí startovné": "Startovné závisí na druhu závodu a kategorii. Na České lize je to zpravidla 400 Kč, na Českém poháru 500 Kč.",
                "kdo má startovní číslo": "Startovní číslo je přiděleno každému jezdci po registraci. Přehled startovních čísel najdeš v seznamu přihlášených jezdců na stránce závodu."
            }

            match = re.search(r"(startovní\s+)?číslo\s+(\d+)", user_message.lower())
            if match:
                plate = match.group(2)
                rider = Rider.objects.filter(plate=plate, is_active=True).first()
                if rider:
                    answer = f"Startovní číslo {plate} má {rider.first_name} {rider.last_name} z klubu {rider.club}."
                else:
                    answer = f"Startovní číslo {plate} nebylo nalezeno v seznamu jezdců."
            else:
                chip_match = re.search(r"(komu patří|kdo má|čí je)?\s*čip\s*([A-Z]{2}-\d{5})", user_message, re.IGNORECASE)
                if chip_match:
                    chip_number = chip_match.group(2)
                    rider = Rider.objects.filter(
                        models.Q(transponder_20=chip_number) | models.Q(transponder_24=chip_number)
                    ).first()
                    if rider:
                        answer = f"Čip {chip_number} patří jezdci {rider.first_name} {rider.last_name} z klubu {rider.club}."
                    else:
                        answer = f"Čip {chip_number} nebyl nalezen v seznamu jezdců."
                elif user_message.lower() in faq:
                    answer = faq[user_message.lower()]
                else:
                    response = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "mistralai/mistral-7b-instruct",
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "Jsi přátelský chatbot pro web České BMX komunity. Odpovídej stejným jazykem, jakým je dotaz. Buď stručný, přehledný a věcný."
                                },
                                {
                                    "role": "user",
                                    "content": user_message
                                }
                            ]
                        }
                    )

                    data = response.json()
                    if "choices" in data:
                        answer = data["choices"][0]["message"]["content"]
                    elif "error" in data:
                        answer = f"Externí model odmítl odpověď: {data['error'].get('message', 'Neznámá chyba')}"
                    else:
                        answer = "Odpověď od modelu nebyla ve správném formátu."

            print("Dotaz:", user_message)
            print("Odpověď:", answer)

            # Uložení do logu
            ChatLog.objects.create(
                user=request.user if request.user.is_authenticated else None,
                message=user_message,
                response=answer
            )

            return Response({"reply": answer})

        except Exception as e:
            logger.error(f"Chyba v ChatbotAPIView: {str(e)}")
            return Response({"error": "Došlo k chybě při zpracování vaší žádosti."}, status=500)