import logging
from django.shortcuts import render
from django.utils.timezone import now, timedelta
from django.db.models import Count
from .models import Visit

logger = logging.getLogger(__name__)

def visit_stats(request):
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
    logger.debug(f"User-Agent: {user_agent}")

    last_days = 7  # počet dní pro statistiku
    time_threshold = now() - timedelta(days=last_days)

    total_visits = Visit.objects.filter(timestamp__gte=time_threshold).count()
    unique_visits = Visit.objects.filter(timestamp__gte=time_threshold).values('ip_address').distinct().count()

    device_counts = list(
        Visit.objects
        .filter(timestamp__gte=time_threshold)
        .values('device_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    country_counts = list(
        Visit.objects
        .filter(timestamp__gte=time_threshold)
        .values('location')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    top_locations = [
        ((entry['location'] or 'Neznámá lokalita'), entry['count'])
        for entry in country_counts
    ]
    device_stats = [
        ((entry['device_type'] or 'Neznámé zařízení'), entry['count'])
        for entry in device_counts
    ]

    context = {
        'total_visits': total_visits,
        'unique_visits': unique_visits,
        'last_days': last_days,
        'top_locations': top_locations,
        'device_stats': device_stats,
    }
    return render(request, 'visit_stats.html', context)
