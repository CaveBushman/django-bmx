from django.shortcuts import render

# Create your views here.

def finance_admin(request):

    data={}

    return render(request, "finance/finance.html", data)