from django.shortcuts import render, get_object_or_404, redirect
from django.core.cache import cache
from django.core.paginator import Paginator
from django.conf import settings
from django.utils.translation import get_language
from event.models import Event, SeasonSettings
from event.func import update_cart
from rider.models import Rider
from news.models import News, Downloads, _AUDIO_LANGS
from news.cache import homepage_data_cache_key
from club.models import Club
from datetime import date
from django.http import FileResponse, Http404
from django.db.models import F, Q
import mimetypes
import os
import re
from theme.models import Sponsor
from bmx.html_sanitizer import sanitize_rich_html

_SUPPORTED_CONTENT_LANGS = {"cs"} | set(_AUDIO_LANGS)

_EMPTY_P_RE = re.compile(r'<p>(\s|&nbsp;|<br\s*/?>)*</p>', re.IGNORECASE)

def _strip_empty_paragraphs(html: str) -> str:
    if not html:
        return html
    return _EMPTY_P_RE.sub('', html)


def _sanitize_news_for_render(article):
    article.perex = sanitize_rich_html(article.perex)
    article.content = sanitize_rich_html(article.content)
    return article


def _sanitize_download_for_render(document):
    document.description = sanitize_rich_html(document.description)
    return document


def homepage_view(request):
    this_year = date.today().year
    today = date.today()
    cache_key = homepage_data_cache_key(today)
    content = cache.get(cache_key)

    if content is None:
        events_sum = Event.objects.filter(date__year=str(this_year), canceled=False).count()
        riders_sum = Rider.sum_of_riders()
        clubs_sum = Club.active_club() - 1  # odečítám "Bez klubové příslušnosti"
        homepage_news = list(
            News.objects.filter(published=True, on_homepage=True)
            .select_related("created")
            .prefetch_related("tags")
            .order_by("-publish_date", "-id")
        )
        homepage_news = [_sanitize_news_for_render(article) for article in homepage_news]
        sponsors = list(
            Sponsor.objects.filter(
                is_published=True,
                valid_from__lte=today,
            ).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today))
        )
        championship_men_leader = Rider.objects.select_related("club").filter(
            is_active=True,
            is_approved=True,
            class_20__in=["Men Junior", "Men Under 23", "Men Elite"],
        ).order_by("-points_20", "last_name", "first_name").first()
        championship_women_leader = Rider.objects.select_related("club").filter(
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

    # Jazykové zpracování titulků a prefixů pro homepage články (per-request, ne v cache)
    lang = (get_language() or "cs").split("-")[0].lower()
    if lang not in _SUPPORTED_CONTENT_LANGS:
        lang = "cs"
    for article in content.get("homepage_news", []):
        article.display_title = article.get_localized("title", lang)
        article.display_perex = article.get_localized("perex", lang)

    if request.user.is_authenticated:
        update_cart(request)
    return render(request, "homepage.html", content)


def prvi_zavod_view(request):
    return render(request, 'prvni_zavod.html')


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
    cache_ttl = getattr(settings, "CACHE_TTL_LONG", 30 * 60)

    lang = (get_language() or "cs").split("-")[0].lower()
    if lang not in _SUPPORTED_CONTENT_LANGS:
        lang = "cs"

    # Výpis potřebuje jen titulek a perex v aktivním jazyce — obsah a překlady
    # ostatních jazyků se nenačítají (jinak by se do cache tahaly megabajty textu).
    unused_fields = ["content", *(f"content_{code}" for code in _AUDIO_LANGS)]
    unused_fields += [
        f"{field}_{code}" for field in ("title", "perex") for code in _AUDIO_LANGS if code != lang
    ]
    qs = (
        News.objects.filter(published=True)
        .select_related("created")
        .prefetch_related("tags")
        .defer(*unused_fields)
        .order_by("-publish_date", "-id")
    )

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(perex__icontains=query))
        total = qs.count()
        sum_of_news = News.sum_of_news()
    else:
        total = cache.get("news_list_count")
        if total is None:
            total = News.sum_of_news()
            cache.set("news_list_count", total, cache_ttl)
        sum_of_news = total

    # Počet známe předem, takže get_page() nevolá COUNT a stránka je jen líný řez querysetu.
    paginator = Paginator(qs, ARTICLES_PER_PAGE)
    paginator.count = total
    news_page = paginator.get_page(request.GET.get("page", 1))

    # Cachujeme jen seznam článků aktuální stránky (ne Page/Paginator s querysetem),
    # klíč je normalizované číslo stránky a výsledky hledání se necachují.
    cache_key = None if query else f"news_list:{lang}:{news_page.number}"
    articles = cache.get(cache_key) if cache_key else None
    if articles is None:
        articles = list(news_page.object_list)
        for article in articles:
            article.display_title = article.get_localized("title", lang)
            article.display_perex = sanitize_rich_html(article.get_localized("perex", lang))
        if cache_key:
            cache.set(cache_key, articles, cache_ttl)
    news_page.object_list = articles

    total_pages = paginator.num_pages
    start_page = max(1, news_page.number - (PAGINATION_WINDOW // 2))
    end_page = min(total_pages, start_page + PAGINATION_WINDOW - 1)
    if (end_page - start_page + 1) < PAGINATION_WINDOW:
        start_page = max(1, end_page - PAGINATION_WINDOW + 1)

    data = {
        "news": news_page,
        "sum_of_news": sum_of_news,
        "page_numbers": range(start_page, end_page + 1),
    }
    return render(request, "news/news-list.html", data)


def news_detail_view(request, slug):
    # Podpora pro staré odkazy s ID (číslo) i nové se slugem v jednom dotazu.
    # Vždy ale přesměrujeme na kanonickou slug URL, pokud ji článek má.
    query = Q(slug=slug)
    if slug.isdigit():
        query |= Q(pk=int(slug))

    # Nezveřejněné články vidí jen redakce (náhled před publikací).
    is_preview_allowed = request.user.is_authenticated and request.user.is_staff
    articles = News.objects.filter(query)
    if not is_preview_allowed:
        articles = articles.filter(published=True)
    news = articles.first()
    if not news:
        raise Http404("Článek nebyl nalezen.")

    if news.slug and news.slug != slug:
        return redirect(news.get_absolute_url(), permanent=True)

    # Přičti zhlédnutí (náhledy redakce se nepočítají)
    if news.published:
        news.increment_views()
    news = _sanitize_news_for_render(news)

    # Jazykový obsah — detekujeme aktivní jazyk z LocaleMiddleware
    lang = (get_language() or "cs").split("-")[0].lower()
    if lang not in _SUPPORTED_CONTENT_LANGS:
        lang = "cs"

    display_title = news.get_localized("title", lang)
    display_perex = _strip_empty_paragraphs(news.get_localized("perex", lang))
    display_content = _strip_empty_paragraphs(news.get_localized("content", lang))
    display_audio_url = news.get_audio_url(lang)

    queryset = {
        'news': news,
        'display_title': display_title,
        'display_perex': display_perex,
        'display_content': display_content,
        'display_audio_url': display_audio_url,
        'display_lang': lang,
        'structured_data': news.get_structured_data(lang),
        "absolute_image_url": request.build_absolute_uri(news.photo_01_url) if news.photo_01_url else None,
    }
    return render(request, 'news/news-detail.html', queryset)


def downloads_view(request):
    documents = [_sanitize_download_for_render(document) for document in Downloads.objects.filter(published=True).prefetch_related("tags")]
    categories = ['Pro jezdce', 'Pro kluby', 'Pro rozhodčí']
    data = {'documents': documents, 'categories': categories}
    return render(request, 'downloads.html', data )

def download_file_view(request, pk):
    document = get_object_or_404(Downloads, pk=pk, published=True)

    if not document.path:
        raise Http404("Soubor nebyl nalezen.")

    # Atomické zvýšení počtu stažení, aby se předešlo race conditions
    Downloads.objects.filter(pk=pk).update(downloads_count=F("downloads_count") + 1)

    try:
        file_name = os.path.basename(document.path.name)
        file_handle = document.path.open("rb")
    except (ValueError, FileNotFoundError, OSError):
        raise Http404("Soubor nebyl nalezen.")

    # Určení MIME typu
    mime_type, _ = mimetypes.guess_type(file_name)

    # Odpověď se souborem
    response = FileResponse(file_handle, content_type=mime_type or "application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    return response
