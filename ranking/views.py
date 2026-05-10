from django.shortcuts import render
from django.core.cache import cache
from django.conf import settings as django_settings
from rider.models import Rider
from .ranking import Categories
import re

_CACHE_MEDIUM = getattr(django_settings, "CACHE_TTL_MEDIUM", 5 * 60)


def ranking_view(request):
    categories = Categories.get_categories()
    default_category = "Men Under 23"
    category_input = request.GET.get("category", "").strip()
    category_value = category_input if category_input in categories else default_category
    invalid_category = bool(category_input and category_input not in categories)

    if re.search("Cruiser", category_value):
        results = (
            Rider.objects.select_related("club")
            .only(
                "uci_id",
                "first_name",
                "last_name",
                "club__team_name",
                "photo",
                "ranking_24",
                "points_24",
                "class_24",
                "is_active",
                "is_approved",
            )
            .filter(
                class_24=category_value[8:],
                is_active=1,
                is_approved=1,
            )
            .order_by("-points_24", "last_name", "first_name")
            .exclude(points_24=0)
        )
        cruiser = 1
    else:
        results = (
            Rider.objects.select_related("club")
            .only(
                "uci_id",
                "first_name",
                "last_name",
                "club__team_name",
                "photo",
                "ranking_20",
                "points_20",
                "class_20",
                "is_active",
                "is_approved",
            )
            .filter(
                class_20=category_value,
                is_active=1,
                is_approved=1,
            )
            .order_by("-points_20", "last_name", "first_name")
            .exclude(points_20=0)
        )
        cruiser = 0

    data = {
        "categories": categories,
        "results": results,
        "category": category_value.upper(),
        "selected_category": category_value,
        "cruiser": cruiser,
        "invalid_category": invalid_category,
    }

    leaderboard_size = results.count()
    if leaderboard_size:
        leader = results[0]
        leader_points = leader.points_24 if cruiser else leader.points_20
    else:
        leader_points = 0

    data.update({
        'leaderboard_size': leaderboard_size,
        'leader_points': leader_points,
        'categories_count': len(categories),
    })

    cache_key = f"ranking_{category_value}"
    cached = cache.get(cache_key)
    if cached is None:
        # Materializujeme queryset před uložením do cache
        data['results'] = list(data['results'])
        cache.set(cache_key, data, _CACHE_MEDIUM)
    else:
        data = cached

    return render(request, 'ranking/ranking.html', data)
