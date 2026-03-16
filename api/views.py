from django.db import models
from chat.models import ChatLog
from django.conf import settings
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticated, AllowAny
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


logger = logging.getLogger(__name__)


class RiderList(generics.ListAPIView):
    """API for list of all active BMX riders """
    queryset = Rider.objects.filter(is_active=True)
    serializer_class = RiderSerializer
    permission_classes = [IsAuthenticated]


class RiderDetail(generics.RetrieveAPIView):
    """API for riders detail"""
    queryset = Rider.objects.all()
    serializer_class = RiderSerializer
    lookup_field = "uci_id"
    permission_classes = [IsAuthenticated]


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
    """Jednoduchý chatbot endpoint s fallbackem na OpenAI.

    Bezpečnostní opatření:
    - Vyhledávání jezdců (plate, chip) vyžaduje přihlášení — bez auth vrací stejnou
      obecnou zprávu bez ohledu na to, zda jezdec existuje (zamezení enumerace).
    - Rate limit: max 20 dotazů za minutu na IP adresu (cache-based).
    - Max délka zprávy: 500 znaků.
    """
    permission_classes = [AllowAny]

    # Maximální počet dotazů za minutu na jednu IP
    RATE_LIMIT = 20
    RATE_WINDOW = 60  # sekund

    def _check_rate_limit(self, request) -> bool:
        """Vrátí True pokud je limit překročen, False pokud je dotaz povolen."""
        from django.core.cache import cache
        ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "unknown"))
        ip = ip.split(",")[0].strip()  # X-Forwarded-For může obsahovat více IP
        cache_key = f"chatbot_rl_{ip}"
        count = cache.get(cache_key, 0)
        if count >= self.RATE_LIMIT:
            return True
        cache.set(cache_key, count + 1, timeout=self.RATE_WINDOW)
        return False

    def post(self, request):
        # Rate limiting
        if self._check_rate_limit(request):
            logger.warning(f"Chatbot rate limit překročen pro IP {request.META.get('REMOTE_ADDR')}")
            return Response({"error": "Příliš mnoho dotazů. Zkus to znovu za chvíli."}, status=429)

        try:
            user_message = request.data.get("message", "").strip()

            # Validace délky zprávy
            if len(user_message) > 500:
                return Response({"error": "Zpráva je příliš dlouhá (max 500 znaků)."}, status=400)

            if not user_message:
                return Response({"error": "Zpráva nesmí být prázdná."}, status=400)

            # Pevně dané FAQ odpovědi (dostupné pro všechny)
            faq = {
                "kdy je další závod": "Podívej se na tomto webu do sekce Kalendář.",
                "kdy se otevře registrace": "Registrace se otevře 1. dubna.",
                "kolik stojí startovné": "Startovné závisí na druhu závodu a kategorii. Na České lize je to zpravidla 400 Kč, na Českém poháru 500 Kč.",
                "kdo má startovní číslo": "Startovní číslo je přiděleno každému jezdci po registraci. Přehled startovních čísel najdeš v seznamu přihlášených jezdců na stránce závodu."
            }

            match = re.search(r"(startovní\s+)?číslo\s+(\d+)", user_message.lower())
            if match:
                # Vyhledávání jezdce podle startovního čísla — pouze pro přihlášené
                if not request.user.is_authenticated:
                    answer = "Pro vyhledávání jezdců se prosím přihlas."
                else:
                    plate = match.group(2)
                    rider = Rider.objects.filter(plate=plate, is_active=True).first()
                    if rider:
                        answer = f"Startovní číslo {plate} má {rider.first_name} {rider.last_name} z klubu {rider.club}."
                    else:
                        # Stejná zpráva pro "neexistuje" i "nenalezeno" — zamezení enumerace
                        answer = "Jezdec s tímto startovním číslem nebyl nalezen."
            else:
                chip_match = re.search(r"(komu patří|kdo má|čí je)?\s*čip\s*([A-Z]{2}-\d{5})", user_message, re.IGNORECASE)
                if chip_match:
                    # Vyhledávání jezdce podle čipu — pouze pro přihlášené
                    if not request.user.is_authenticated:
                        answer = "Pro vyhledávání jezdců se prosím přihlas."
                    else:
                        chip_number = chip_match.group(2)
                        rider = Rider.objects.filter(
                            models.Q(transponder_20=chip_number) | models.Q(transponder_24=chip_number)
                        ).first()
                        if rider:
                            answer = f"Čip {chip_number} patří jezdci {rider.first_name} {rider.last_name} z klubu {rider.club}."
                        else:
                            # Stejná zpráva bez ohledu na existenci — zamezení enumerace
                            answer = "Jezdec s tímto čipem nebyl nalezen."
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

            logger.info(f"Chatbot dotaz od {'přihlášeného uživatele' if request.user.is_authenticated else 'anonyma'}: {user_message[:100]}")

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
