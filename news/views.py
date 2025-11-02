from django.shortcuts import render, get_object_or_404 
from django.http import HttpResponseRedirect
from django.core.paginator import Paginator, EmptyPage
from event.models import Event
from event.func import update_cart
from func.notification import update_plate_notify
from rider.models import Rider
from news.models import News, Downloads
from club.models import Club
from datetime import date
from django.http import FileResponse, Http404
import mimetypes
import os

# Create your views here.

def get_image_dimensions(image_field):
    image = Image.open(BytesIO(image_field.read()))
    return image.width, image.height

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
    content = {'clubs_count': clubs_sum, 'riders_count': riders_sum,
               'races_count': events_sum,
               'homepage_news': homepage_news}
    return render(request, "homepage.html", content)


def rules_view(request):
    return render(request, 'rules.html')



def news_list_view(request):
    ARTICLES_PER_PAGE = 9

    news = News.objects.filter(published=True).order_by('-publish_date')
    sum_of_news = News.sum_of_news()

    # Set up pagination
    paginator = Paginator(news, ARTICLES_PER_PAGE)  # Show 10 news per page
    page_number = request.GET.get('page')  # Get the current page number from query params
    news_page = paginator.get_page(page_number)

    # Define the range of pages to show (here we show 10 pages max)
    start_page = max(1, news_page.number - 5)
    end_page = min(news_page.paginator.num_pages, news_page.number + 4)

    data = {'news': news_page, 'sum_of_news': sum_of_news, 'start_page': start_page, 'end_page': end_page}

    return render(request, 'news/news-list.html', data)


def news_detail_view(request, pk):
    news = get_object_or_404(News, pk=pk)
    # Přičti zhlédnutí
    news.increment_views()
    queryset = {'news': news, "absolute_image_url": request.build_absolute_uri(news.photo_01.url) if news.photo_01 else None}
    return render(request, 'news/news-detail.html', queryset)


def downloads_view(request):
    documents = Downloads.objects.filter(published=True)
    categories = ['Pro jezdce', 'Pro kluby', 'Pro rozhodčí']
    data = {'documents': documents, 'categories': categories}
    return render(request, 'downloads.html', data )

def download_file_view(request, pk):
    document = get_object_or_404(Downloads, pk=pk, published=True)

    if not document.path:
        raise Http404("Soubor nebyl nalezen.")

    # Zvýšení počtu stažení
    document.downloads_count += 1
    document.save(update_fields=["downloads_count"])

    # Cesta k souboru
    file_path = document.path.path
    file_name = os.path.basename(file_path)

    # Určení MIME typu
    mime_type, _ = mimetypes.guess_type(file_path)

    # Odpověď se souborem
    response = FileResponse(open(file_path, "rb"), content_type=mime_type or "application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    return response