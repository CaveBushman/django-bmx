from django.shortcuts import render
from rest_framework.decorators import api_view

from .func import calculate_user_balance, calculate_stripe_fee
from datetime import date

# Create your views here.

def finance_admin(request):

    current_year = date.today().year

    stripe_fee = calculate_stripe_fee(current_year)
    credit = calculate_user_balance()
    data={"credit":credit, "stripe_fee": stripe_fee}

    return render(request, "finance/finance.html", data)