from django.shortcuts import render
from commissar.models import Commissar

def list_of_commisars_view(request):
    commisars = Commissar.objects.filter(is_active=True)
    data = {'commissars': commisars}
    return render(request, 'commissar/commissar-list.html', data)

