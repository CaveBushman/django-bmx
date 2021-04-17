from django.shortcuts import render
from rider.models import Rider
from .ranking import RankingCount, Categories
from event.models import Result
import re
import datetime

# Create your views here.

def RankingView(request):
    global results
    view_data = 0

    categories = Categories.get_categories()

    if request.POST:
        if re.search("Cruiser", request.POST['categoryInput']):
            results = Rider.objects.filter(class_24=request.POST['categoryInput'][9:], is_active=1, is_approwe=1).order_by('-points_24').exclude(points_24=0)
            cruiser = 1
        else:
            results = Rider.objects.filter(class_20=request.POST['categoryInput'], is_active=1, is_approwe=1).order_by('-points_20').exclude(points_20=0)
            cruiser = 0

        view_data = 1
        data = {'categories': categories, 'results': results, 'category': request.POST['categoryInput'], 'view_data': view_data, 'cruiser': cruiser}
    else:
        data = {'categories': categories, 'view_data': view_data,}
    return render(request, 'ranking/ranking.html', data)
