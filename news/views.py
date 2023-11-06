from django.shortcuts import render, get_object_or_404 
from django.http import HttpResponseRedirect
from django.core.paginator import Paginator, EmptyPage
from event.models import Event, Order
from event.func import update_cart
from func.notification import update_plate_notify
from rider.models import Rider
from news.models import News, Downloads
from club.models import Club

from datetime import date


# Create your views here.

def change_theme(request):
    if 'is_dark_mode' in request.session:
        request.session['is_dark_mode'] = not request.session['is_dark_mode']
    else:
        request.session['is_dark_mode'] = True
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

def homepage_view(request):
    this_year = date.today().year
    events_sum = Event.objects.filter(date__year=str(this_year), canceled=False).count
    riders_sum = Rider.sum_of_riders()
    clubs_sum = Club.active_club() - 1  # odečítám "Bez klubové příslušnosti"
    homepage_news = News.objects.order_by('-publish_date').filter(published=True, on_homepage=True)
    update_cart(request)
    update_plate_notify(request)
    content = {'clubs_sum': clubs_sum, 'riders_sum': riders_sum,
               'events_sum': events_sum,
               'homepage_news': homepage_news}
    return render(request, "homepage.html", content)


def rules_view(request):
    return render(request, 'rules.html')


def news_list_view(request):
    ARTICLES_PER_PAGE = 9

    news = News.objects.filter(published=True).order_by('-publish_date')
    sum_of_news = News.sum_of_news()

    news_paginator = Paginator(news, ARTICLES_PER_PAGE)

    page_num = request.GET.get('page', 1)
    page = news_paginator.get_page(page_num)

    data = {'news': page, 'sum_of_news': sum_of_news}

    return render(request, 'news/news-list.html', data)


def news_detail_view(request, pk):
    news = get_object_or_404(News, pk=pk)
    print(news)
    queryset = {'news': news}

    return render(request, 'news/news-detail.html', queryset)


def downloads_view(request):
    documents = Downloads.objects.filter(published=True)
    data = {'documents': documents}

    return render(request, 'downloads.html', data)
