from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from datetime import date, datetime, timedelta
import stripe
import logging
from django.conf import settings

from .func import calculate_user_balance, calculate_stripe_fee
from event.models import CreditTransaction
from accounts.models import Account
from django.db.models import F

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)

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

    if request.method == "POST" and "verify_payments" in request.POST:
        # Manuální ověření plateb za poslední 2 dny
        two_days_ago = timezone.now() - timedelta(days=2)
        credit_transactions = CreditTransaction.objects.filter(
            payment_complete=False,
            transaction_date__gte=two_days_ago,
        )

        verified_count = 0
        for ct in credit_transactions:
            try:
                with transaction.atomic():
                    ct = CreditTransaction.objects.select_for_update().get(id=ct.id)
                    if ct.payment_complete:
                        continue
                    confirm = stripe.checkout.Session.retrieve(ct.transaction_id)
                    if confirm.get("payment_status") == "paid":
                        Account.objects.filter(id=ct.user.id).update(
                            credit=F("credit") + ct.amount
                        )
                        ct.payment_complete = True
                        ct.payment_intent = confirm.get("payment_intent")
                        ct.save()
                        verified_count += 1
                        logger.info(f"Manuálně ověřena platba kreditu: {ct}")
            except Exception as e:
                logger.error(f"Chyba při manuálním ověření kreditu {ct.id}: {e}")

        messages.success(request, f"Ověřeno {verified_count} plateb za kredity za poslední 2 dny.")
        # Aktualizovat data po ověření
        credit = calculate_user_balance()
        data["credit"] = credit

    return render(request, "finance/finance.html", data)
