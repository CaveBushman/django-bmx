from django.shortcuts import render
from django.utils.timezone import now, timedelta
from django.db.models import Count
from .models import Visit

def visit_stats(request):
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
    print(f"📈 User-Agent: {user_agent}")
    
    last_days = 7  # počet dní pro statistiku
    time_threshold = now() - timedelta(days=last_days)

    total_visits = Visit.objects.filter(timestamp__gte=time_threshold).count()
    unique_visits = Visit.objects.filter(timestamp__gte=time_threshold).values('ip_address').distinct().count()

    device_counts = (
        Visit.objects
        .filter(timestamp__gte=time_threshold)
        .annotate(device=Count('device_type'))
        .values('device_type')
        .annotate(count=Count('device_type'))
    )
    for entry in device_counts:
        if not entry['device_type']:
            entry['device_type'] = 'Neznámé zařízení'

    country_counts = (
        Visit.objects
        .filter(timestamp__gte=time_threshold)
        .values('location')
        .annotate(count=Count('location'))
        .order_by('-count')
    )

    user_agent_counts = (
        Visit.objects
        .filter(timestamp__gte=time_threshold)
        .values('user_agent')
        .annotate(count=Count('user_agent'))
        .order_by('-count')
    )

    context = {
        'total_visits': total_visits,
        'unique_visits': unique_visits,
        'last_days': last_days,
        'device_counts': device_counts,
        'location_counts': country_counts,
        'user_agent_counts': user_agent_counts,
    }
    return render(request, 'visit_stats.html', context)