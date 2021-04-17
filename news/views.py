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
    riders_sum = Rider.objects.filter(is_active=True).count
    clubs_sum = Club.active_club()
    articles_sum = News.objects.all().count
    homepage_news = News.objects.order_by('-created_date').filter(published=True, on_homepage=True)

    content = {'clubs_sum': clubs_sum, 'riders_sum': riders_sum,
               'events_sum': events_sum, 'articles_sum': articles_sum,
               'homepage_news': homepage_news}
    return render(request, "pages/homepage.html", content)


def RulesView(request):
    return render(request, 'pages/rules.html')


def NewsListView(request):
    news = News.objects.all().order_by('created_date')
    data = {'news': news}

    return render(request, 'news/news-list.html', data)


def NewsDetailView(request, pk):
    news = get_object_or_404(News, pk=pk)
    print(news)
    queryset = {'news': news}

    return render(request, 'news/news-detail.html', queryset)
