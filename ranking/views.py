from django.shortcuts import render
from rider.models import Rider
from .ranking import Categories
import re



# Create your views here.

def ranking_view(request):
    global results

    categories = Categories.get_categories()
    category_input = request.POST.get("categoryInput", "").strip()

    if request.POST:
        if re.search("Cruiser", category_input):
            results = Rider.objects.filter(class_24=category_input[8:], is_active=1,
                                           is_approved=1).order_by('-points_24').exclude(points_24=0)
            cruiser = 1
        else:
            results = Rider.objects.filter(class_20=category_input, is_active=1, is_approved=1).order_by(
                '-points_20').exclude(points_20=0)
            cruiser = 0

        data = {'categories': categories, 'results': results, 'category': category_input or "MEN UNDER 23",
                'cruiser': cruiser}
    else:
        results = Rider.objects.filter(class_20="Men Under 23", is_active=1, is_approved=1).order_by(
            '-points_20').exclude(points_20=0)
        cruiser = 0
        data = {'categories': categories, 'results': results, 'category': "MEN UNDER 23", 'cruiser': cruiser}

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
    return render(request, 'ranking/ranking.html', data)
