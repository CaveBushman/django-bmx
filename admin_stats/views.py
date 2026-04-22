import logging
from django.shortcuts import render
from django.utils.timezone import now, timedelta, localdate
from django.db.models import Count
from django.db.models.functions import TruncDate
from .models import Visit

logger = logging.getLogger(__name__)

_DEVICE_LABELS = {
    'mobile': 'Mobilní zařízení',
    'tablet': 'Tablet',
    'desktop': 'Desktop',
    'unknown': 'Neznámé zařízení',
}


def visit_stats(request):
    last_days = 7
    time_threshold = now() - timedelta(days=last_days)
    qs = Visit.objects.filter(timestamp__gte=time_threshold)

    total_visits = qs.count()
    unique_visits = qs.values('ip_address').distinct().count()

    yesterday_start = now() - timedelta(days=1)
    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    visits_today = Visit.objects.filter(timestamp__gte=today_start).count()
    visits_yesterday = Visit.objects.filter(timestamp__gte=yesterday_start, timestamp__lt=today_start).count()

    device_counts = list(
        qs.values('device_type').annotate(count=Count('id')).order_by('-count')
    )
    country_counts = list(
        qs.values('location').annotate(count=Count('id')).order_by('-count')
    )
    top_pages = list(
        qs.exclude(path__isnull=True).exclude(path='')
        .values('path')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    daily_raw = {
        entry['date']: entry['count']
        for entry in qs.annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(count=Count('id'))
    }
    today = localdate()
    all_dates = [today - timedelta(days=i) for i in range(last_days - 1, -1, -1)]
    daily_max = max(daily_raw.values(), default=1)
    daily_stats = [
        {'date': d, 'count': daily_raw.get(d, 0)}
        for d in all_dates
    ]

    top_locations = [
        ((entry['location'] or 'Neznámá lokalita'), entry['count'])
        for entry in country_counts
        if entry['location'] and entry['location'] != 'unknown'
    ] or [('Neznámá lokalita', total_visits)]

    device_stats = [
        (_DEVICE_LABELS.get(entry['device_type'] or 'unknown', entry['device_type']), entry['count'])
        for entry in device_counts
    ]

    context = {
        'total_visits': total_visits,
        'unique_visits': unique_visits,
        'last_days': last_days,
        'visits_today': visits_today,
        'visits_yesterday': visits_yesterday,
        'top_locations': top_locations,
        'device_stats': device_stats,
        'daily_stats': daily_stats,
        'daily_max': daily_max,
        'top_pages': top_pages,
    }
    return render(request, 'visit_stats.html', context)
