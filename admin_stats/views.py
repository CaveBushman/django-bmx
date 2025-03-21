from django.shortcuts import render
from django.utils.timezone import now, timedelta
from .models import Visit

def visit_stats(request):
    last_days = 7  # počet dní pro statistiku
    time_threshold = now() - timedelta(days=last_days)

    total_visits = Visit.objects.filter(timestamp__gte=time_threshold).count()
    unique_visits = Visit.objects.filter(timestamp__gte=time_threshold).values('ip_address').distinct().count()

    context = {
        'total_visits': total_visits,
        'unique_visits': unique_visits,
        'last_days': last_days,
    }
    return render(request, 'visit_stats.html', context)