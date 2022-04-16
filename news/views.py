from django.shortcuts import render, get_object_or_404
from event.models import Event
from rider.models import Rider
from news.models import News
from club.models import Club

from datetime import date


# Create your views here.

def HomepageView(request):
    this_year = date.today().year
    events_sum = Event.objects.filter(date__year=str(this_year), canceled=False).count
    riders_sum = Rider.sum_of_riders()
    clubs_sum = Club.active_club()
    homepage_news = News.objects.order_by('-publish_date').filter(published=True, on_homepage=True)

    content = {'clubs_sum': clubs_sum, 'riders_sum': riders_sum,
               'events_sum': events_sum,
               'homepage_news': homepage_news}
    return render(request, "homepage.html", content)


def RulesView(request):
    return render(request, 'rules.html')


def NewsListView(request):
    news = News.objects.all().order_by('-publish_date')
    sum_of_news = News.sum_of_news()
    data = {'news': news, 'sum_of_news':sum_of_news}

    return render(request, 'news/news-list.html', data)


def NewsDetailView(request, pk):
    news = get_object_or_404(News, pk=pk)
    print(news)
    queryset = {'news': news}

    return render(request, 'news/news-detail.html', queryset)
