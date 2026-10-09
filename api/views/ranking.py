import re

from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, inline_serializer

from rider.models import Rider
from ranking.ranking import Categories


from api.views._common import *  # noqa: F401,F403


class RankingCategoryListAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            name="RankingCategories",
            fields={"categories": serializers.ListField(child=serializers.CharField())},
        )
    )
    def get(self, request):
        categories = Categories.get_categories()
        return Response({"categories": categories})


class RankingAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        categories = Categories.get_categories()
        default_category = "Men Under 23"
        category_input = request.query_params.get("category", "").strip()
        category_value = category_input if category_input in categories else default_category

        if re.search("Cruiser", category_value):
            qs = (
                Rider.objects.select_related("club")
                .only(
                    "uci_id", "first_name", "last_name",
                    "club__team_name", "photo",
                    "ranking_24", "points_24", "class_24",
                    "is_active", "is_approved",
                )
                .filter(class_24=category_value[8:], is_active=True, is_approved=True)
                .order_by("-points_24", "last_name", "first_name")
                .exclude(points_24=0)
            )
            cruiser = True
        else:
            qs = (
                Rider.objects.select_related("club")
                .only(
                    "uci_id", "first_name", "last_name",
                    "club__team_name", "photo",
                    "ranking_20", "points_20", "class_20",
                    "is_active", "is_approved",
                )
                .filter(class_20=category_value, is_active=True, is_approved=True)
                .order_by("-points_20", "last_name", "first_name")
                .exclude(points_20=0)
            )
            cruiser = False

        results = [
            {
                "rank": i,
                "uci_id": r.uci_id,
                "first_name": r.first_name,
                "last_name": r.last_name,
                "club": r.club.team_name if r.club else None,
                "photo_url": r.photo_url,
                "points": r.points_24 if cruiser else r.points_20,
                "ranking": r.ranking_24 if cruiser else r.ranking_20,
            }
            for i, r in enumerate(qs, 1)
        ]

        return Response({
            "category": category_value,
            "cruiser": cruiser,
            "count": len(results),
            "results": results,
        })

__all__ = ['RankingCategoryListAPIView', 'RankingAPIView']
