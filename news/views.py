from django.shortcuts import render, get_object_or_404, redirect
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.core.paginator import Paginator, EmptyPage
from django.conf import settings
from event.models import Event, SeasonSettings
from event.func import update_cart
from rider.rider import update_plate_notify
from rider.models import Rider
from news.models import News, Downloads
from club.models import Club
from datetime import date
from django.http import FileResponse, Http404
from django.db.models import F, Q
import mimetypes
import os
from theme.models import Sponsor

# Create your views here.

def get_image_dimensions(image_field):
    image = Image.open(BytesIO(image_field.read()))
    return image.width, image.height


def homepage_view(request):
    this_year = date.today().year
    today = date.today()
    cache_key = f"homepage:view-data:{this_year}:{today.isoformat()}"
    content = cache.get(cache_key)

    if content is None:
        events_sum = Event.objects.filter(date__year=str(this_year), canceled=False).count()
        riders_sum = Rider.sum_of_riders()
        clubs_sum = Club.active_club() - 1  # odečítám "Bez klubové příslušnosti"
        homepage_news = list(
            News.objects.filter(published=True, on_homepage=True)
            .select_related("created")
            .prefetch_related("tags")
            .order_by("-publish_date")
        )
        sponsors = list(
            Sponsor.objects.filter(
                is_published=True,
                valid_from__lte=today,
            ).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today))
        )
        championship_men_leader = Rider.objects.filter(
            is_active=True,
            is_approved=True,
            class_20__in=["Men Junior", "Men Under 23", "Men Elite"],
        ).order_by("-points_20", "last_name", "first_name").first()
        championship_women_leader = Rider.objects.filter(
            is_active=True,
            is_approved=True,
            class_20__in=["Women Junior", "Women Under 23", "Women Elite"],
        ).order_by("-points_20", "last_name", "first_name").first()
        content = {
            "clubs_count": clubs_sum,
            "riders_count": riders_sum,
            "races_count": events_sum,
            "homepage_news": homepage_news,
            "sponsors": sponsors,
            "championship_men_leader": championship_men_leader,
            "championship_women_leader": championship_women_leader,
        }
        cache.set(cache_key, content, settings.HOMEPAGE_DATA_CACHE_SECONDS)

    update_cart(request)
    update_plate_notify(request)
    return render(request, "homepage.html", content)


def rules_view(request):
    current_year = date.today().year
    season_settings = (
        SeasonSettings.objects.filter(year=current_year).first()
        or SeasonSettings.objects.order_by("-year").first()
    )
    content = {
        "transponder_price": season_settings.transponder_price if season_settings else 1900,
        "bmx_rules_link": season_settings.bmx_rules_link if season_settings else "",
    }
    return render(request, 'rules.html', content)



def news_list_view(request):
    ARTICLES_PER_PAGE = 10
    PAGINATION_WINDOW = 10

    news = News.objects.filter(published=True).order_by('-publish_date')
    sum_of_news = News.sum_of_news()

    # Set up pagination
    paginator = Paginator(news, ARTICLES_PER_PAGE)  # Show 10 news per page
    page_number = request.GET.get('page')  # Get the current page number from query params
    news_page = paginator.get_page(page_number)

    total_pages = news_page.paginator.num_pages
    start_page = max(1, news_page.number - (PAGINATION_WINDOW // 2))
    end_page = min(total_pages, start_page + PAGINATION_WINDOW - 1)

    if (end_page - start_page + 1) < PAGINATION_WINDOW:
        start_page = max(1, end_page - PAGINATION_WINDOW + 1)

    page_numbers = range(start_page, end_page + 1)

    data = {
        'news': news_page,
        'sum_of_news': sum_of_news,
        'page_numbers': page_numbers,
    }

    return render(request, 'news/news-list.html', data)


def news_detail_view(request, slug):
    # Podpora pro staré odkazy s ID (číslo) i nové se slugem v jednom dotazu.
    # Vždy ale přesměrujeme na kanonickou slug URL, pokud ji článek má.
    query = Q(slug=slug)
    if slug.isdigit():
        query |= Q(pk=int(slug))

    news = News.objects.filter(query).first()
    if not news:
        raise Http404("Článek nebyl nalezen.")

    if news.slug and news.slug != slug:
        return redirect(news.get_absolute_url(), permanent=True)

    # Přičti zhlédnutí
    news.increment_views()
    queryset = {
        'news': news,
        "absolute_image_url": request.build_absolute_uri(news.photo_01_url) if news.photo_01_url else None,
    }
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

    # Atomické zvýšení počtu stažení, aby se předešlo race conditions
    Downloads.objects.filter(pk=pk).update(downloads_count=F("downloads_count") + 1)

    # Cesta k souboru
    file_path = document.path.path
    file_name = os.path.basename(file_path)

    # Určení MIME typu
    mime_type, _ = mimetypes.guess_type(file_path)

    # Odpověď se souborem
    response = FileResponse(open(file_path, "rb"), content_type=mime_type or "application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    return response
