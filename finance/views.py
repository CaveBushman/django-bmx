from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test

from .func import calculate_user_balance, calculate_stripe_fee
from datetime import date

# Create your views here.

def _is_finance_admin(user):
    return user.is_authenticated and user.is_admin


@login_required(login_url="/login/")
@user_passes_test(_is_finance_admin, login_url="/login/")
def finance_admin(request):

    current_year = date.today().year

    stripe_fee = calculate_stripe_fee(current_year)
    credit = calculate_user_balance()
    data={"credit":credit, "stripe_fee": stripe_fee}

    return render(request, "finance/finance.html", data)
