from django.shortcuts import render
from models import Commissar

# Create your views here.

def list_of_commisars_view (request):
    commisars = Commissar.objects.filter(is_active = True)
    data = {'commissars':commisars}
    pass


