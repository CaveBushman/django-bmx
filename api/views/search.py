
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, inline_serializer

from rider.models import Rider
from event.models import Event


from api.views._common import *  # noqa: F401,F403


class GlobalSearchAPIView(APIView):
    """
    Fulltextové hledání přes jezdce, závody a novinky.

    GET /api/v1/search/?q=novak&types=riders,events,news&limit=5
    """
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, description="Hledaný výraz (min. 2 znaky)"),
            OpenApiParameter("types", OpenApiTypes.STR, description="Typy výsledků: riders,events,news (výchozí: vše)"),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Max. výsledků na typ (výchozí: 5, max: 20)"),
        ],
        responses={200: inline_serializer(
            name="SearchResults",
            fields={
                "query": serializers.CharField(),
                "riders": serializers.ListField(child=serializers.DictField()),
                "events": serializers.ListField(child=serializers.DictField()),
                "news": serializers.ListField(child=serializers.DictField()),
            },
        )},
    )
    def get(self, request):
        from django.db.models import Q as DQ
        from bmx.text_normalization import normalize_search_text

        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response({"query": q, "riders": [], "events": [], "news": []})

        types_param = request.query_params.get("types", "riders,events,news")
        active_types = {t.strip() for t in types_param.split(",")}
        try:
            limit = min(int(request.query_params.get("limit", 5)), 20)
        except (ValueError, TypeError):
            limit = 5

        results = {"query": q, "riders": [], "events": [], "news": []}
        q_normalized = normalize_search_text(q)

        if "riders" in active_types:
            rider_qs = (
                Rider.objects.filter(is_active=True, is_approved=True)
                .filter(
                    DQ(search_text_normalized__icontains=q_normalized)
                    | DQ(first_name__icontains=q)
                    | DQ(last_name__icontains=q)
                )
                .select_related("club")[:limit]
            )
            results["riders"] = [
                {
                    "uci_id": r.uci_id,
                    "first_name": r.first_name,
                    "last_name": r.last_name,
                    "club": str(r.club or ""),
                    "class_20": r.class_20 or "",
                    "plate": r.plate_display,
                }
                for r in rider_qs
            ]

        if "events" in active_types:
            event_qs = (
                Event.objects.filter(
                    DQ(name__icontains=q) | DQ(organizer__team_name__icontains=q)
                )
                .select_related("organizer")
                .order_by("-date")[:limit]
            )
            results["events"] = [
                {
                    "id": e.id,
                    "name": e.name,
                    "date": e.date.isoformat() if e.date else "",
                    "organizer": str(e.organizer or ""),
                    "type": e.type_for_ranking,
                    "canceled": e.canceled,
                }
                for e in event_qs
            ]

        if "news" in active_types:
            from news.models import News
            news_qs = (
                News.objects.filter(published=True)
                .filter(DQ(title__icontains=q) | DQ(perex__icontains=q))
                .order_by("-publish_date", "-id")[:limit]
            )
            results["news"] = [
                {
                    "id": n.id,
                    "title": n.title,
                    "perex": (n.perex or "")[:160],
                    "created": n.created_date.isoformat(),
                    "slug": n.slug,
                }
                for n in news_qs
            ]

        return Response(results)

__all__ = ['GlobalSearchAPIView']
