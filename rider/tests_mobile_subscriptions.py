"""
Komplexní testy pro mobilní předplatné a promo kódy.

Pokrývá:
- PromoCode.is_valid() a calculate_discount()
- purchase_mobile_app_subscription() – happy path, nedostatek kreditu, duplicita, promo kód
- cancel / resume předplatného
- renew_due_mobile_app_subscriptions() – prodloužení, nedostatek kreditu, vypnutý auto-renew
- Výpočet kreditu zahrnuje MobileAppCharge
- Web view /rider/mobile-app-subscription (GET + POST activate/cancel/resume)
- Admin view /rider/promo-codes (GET + POST generate/activate/deactivate)
- API GET/POST/DELETE /api/subscriptions/mobile/
- API POST /api/promo-codes/validate/
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from club.models import Club
from event.credit import calculate_user_balance
from event.models import CreditTransaction, SeasonSettings
from rider.mobile_subscriptions import (
    cancel_mobile_app_subscription,
    get_active_mobile_app_subscription,
    has_active_mobile_app_access,
    purchase_mobile_app_subscription,
    renew_due_mobile_app_subscriptions,
    resume_mobile_app_subscription,
)
from rider.models import (
    MobileAppCharge,
    MobileAppSubscription,
    PromoCode,
    PromoCodeUsage,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Pomocná továrna
# ---------------------------------------------------------------------------

def _make_user(username, *, credit=0, is_staff=False):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="StrongPass123!",
        first_name="Test",
        last_name="User",
    )
    user.is_active = True
    user.is_staff = is_staff
    user.save()
    if credit > 0:
        CreditTransaction.objects.create(
            user=user,
            amount=credit,
            transaction_id=f"tx-{username}",
            payment_complete=True,
        )
        user.credit = credit
        user.save(update_fields=["credit"])
    return user


def _make_season(year=None, price=499):
    year = year or timezone.now().year
    return SeasonSettings.objects.get_or_create(
        year=year,
        defaults={"mobile_app_annual_price": price},
    )[0]


def _make_promo(
    *,
    discount_type=PromoCode.DISCOUNT_FREE,
    discount_value=100,
    product=PromoCode.PRODUCT_MOBILE_APP,
    max_uses=None,
    is_active=True,
    valid_until=None,
):
    return PromoCode.objects.create(
        discount_type=discount_type,
        discount_value=discount_value,
        product=product,
        max_uses=max_uses,
        is_active=is_active,
        valid_until=valid_until,
    )


# ===========================================================================
# 1. PromoCode model — is_valid() a calculate_discount()
# ===========================================================================

class PromoCodeValidityTests(TestCase):
    def test_active_code_is_valid(self):
        promo = _make_promo()
        self.assertTrue(promo.is_valid())

    def test_inactive_code_is_invalid(self):
        promo = _make_promo(is_active=False)
        self.assertFalse(promo.is_valid())

    def test_expired_code_is_invalid(self):
        promo = _make_promo(valid_until=timezone.now() - timedelta(hours=1))
        self.assertFalse(promo.is_valid())

    def test_future_valid_until_is_valid(self):
        promo = _make_promo(valid_until=timezone.now() + timedelta(days=30))
        self.assertTrue(promo.is_valid())

    def test_max_uses_reached_is_invalid(self):
        promo = _make_promo(max_uses=2)
        promo.used_count = 2
        promo.save()
        self.assertFalse(promo.is_valid())

    def test_max_uses_not_reached_is_valid(self):
        promo = _make_promo(max_uses=5)
        promo.used_count = 3
        promo.save()
        self.assertTrue(promo.is_valid())

    def test_unlimited_uses_always_valid(self):
        promo = _make_promo(max_uses=None)
        promo.used_count = 9999
        promo.save()
        self.assertTrue(promo.is_valid())


class PromoCodeDiscountTests(TestCase):
    def test_free_gives_full_price(self):
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FREE)
        self.assertEqual(promo.calculate_discount(499), 499)

    def test_percent_calculates_correctly(self):
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_PERCENT, discount_value=20)
        self.assertEqual(promo.calculate_discount(500), 100)

    def test_fixed_calculates_correctly(self):
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FIXED, discount_value=100)
        self.assertEqual(promo.calculate_discount(499), 100)

    def test_fixed_cannot_exceed_price(self):
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FIXED, discount_value=1000)
        self.assertEqual(promo.calculate_discount(499), 499)


# ===========================================================================
# 2. purchase_mobile_app_subscription()
# ===========================================================================

class PurchaseMobileAppSubscriptionTests(TestCase):
    def setUp(self):
        self.season = _make_season(price=499)

    def test_purchase_creates_active_subscription(self):
        user = _make_user("buyer1", credit=500)
        sub, created = purchase_mobile_app_subscription(user)

        self.assertTrue(created)
        self.assertEqual(sub.status, MobileAppSubscription.STATUS_ACTIVE)
        self.assertTrue(sub.auto_renew)
        self.assertEqual(sub.monthly_price, 499)

    def test_purchase_deducts_credit(self):
        user = _make_user("buyer2", credit=500)
        purchase_mobile_app_subscription(user)

        user.refresh_from_db()
        self.assertEqual(user.credit, 1)

    def test_purchase_creates_charge_record(self):
        user = _make_user("buyer3", credit=500)
        purchase_mobile_app_subscription(user)

        charge = MobileAppCharge.objects.get(user=user)
        self.assertEqual(charge.amount, 499)
        self.assertEqual(charge.reason, MobileAppCharge.REASON_INITIAL)

    def test_subscription_period_is_365_days(self):
        now = timezone.now()
        user = _make_user("buyer4", credit=500)
        sub, _ = purchase_mobile_app_subscription(user, at_time=now)

        delta = sub.expires_at - sub.starts_at
        self.assertGreaterEqual(delta.days, 364)

    def test_insufficient_credit_raises(self):
        user = _make_user("broke1", credit=100)

        with self.assertRaises(ValueError, msg="Nedostatek kreditu"):
            purchase_mobile_app_subscription(user)

    def test_duplicate_purchase_returns_existing(self):
        user = _make_user("buyer5", credit=1000)
        sub1, created1 = purchase_mobile_app_subscription(user)
        sub2, created2 = purchase_mobile_app_subscription(user)

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(sub1.pk, sub2.pk)
        self.assertEqual(MobileAppCharge.objects.filter(user=user).count(), 1)

    def test_no_season_raises(self):
        self.season.delete()
        user = _make_user("noseason1", credit=500)

        with self.assertRaises(ValueError):
            purchase_mobile_app_subscription(user)

    def test_free_promo_code_zero_credit_needed(self):
        user = _make_user("promo1", credit=0)
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FREE)

        sub, created = purchase_mobile_app_subscription(user, promo_code_str=promo.code)

        self.assertTrue(created)
        self.assertEqual(sub.status, MobileAppSubscription.STATUS_ACTIVE)
        user.refresh_from_db()
        self.assertEqual(user.credit, 0)

    def test_percent_promo_reduces_charge(self):
        user = _make_user("promo2", credit=250)
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_PERCENT, discount_value=50)

        sub, created = purchase_mobile_app_subscription(user, promo_code_str=promo.code)

        self.assertTrue(created)
        charge = MobileAppCharge.objects.get(user=user)
        # discount = int(499 * 50 / 100) = int(249.5) = 249 → charge = 499 - 249 = 250
        self.assertEqual(charge.amount, 250)
        user.refresh_from_db()
        self.assertEqual(user.credit, 0)

    def test_fixed_promo_reduces_charge(self):
        user = _make_user("promo3", credit=100)
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FIXED, discount_value=400)

        sub, created = purchase_mobile_app_subscription(user, promo_code_str=promo.code)

        self.assertTrue(created)
        charge = MobileAppCharge.objects.get(user=user)
        self.assertEqual(charge.amount, 99)  # 499 - 400 = 99
        user.refresh_from_db()
        self.assertEqual(user.credit, 1)

    def test_promo_usage_is_recorded(self):
        user = _make_user("promo4", credit=500)
        promo = _make_promo()

        purchase_mobile_app_subscription(user, promo_code_str=promo.code)

        self.assertTrue(PromoCodeUsage.objects.filter(promo_code=promo, user=user).exists())
        promo.refresh_from_db()
        self.assertEqual(promo.used_count, 1)

    def test_same_promo_code_cannot_be_used_twice_by_same_user(self):
        user = _make_user("promo5", credit=500)
        promo = _make_promo()
        purchase_mobile_app_subscription(user, promo_code_str=promo.code)

        # Zruš a znovu zkus aktivovat se stejným kódem
        sub = get_active_mobile_app_subscription(user)
        cancel_mobile_app_subscription(sub)
        # Nechej předplatné expirovat
        MobileAppSubscription.objects.filter(user=user).update(
            expires_at=timezone.now() - timedelta(seconds=1),
            status=MobileAppSubscription.STATUS_EXPIRED,
        )

        with self.assertRaises(ValueError, msg="Tento promo kód jste již použili"):
            purchase_mobile_app_subscription(user, promo_code_str=promo.code)

    def test_invalid_promo_code_raises(self):
        user = _make_user("promo6", credit=500)

        with self.assertRaises(ValueError, msg="Promo kód neexistuje"):
            purchase_mobile_app_subscription(user, promo_code_str="NEEXISTUJE")

    def test_expired_promo_raises(self):
        user = _make_user("promo7", credit=500)
        promo = _make_promo(valid_until=timezone.now() - timedelta(hours=1))

        with self.assertRaises(ValueError):
            purchase_mobile_app_subscription(user, promo_code_str=promo.code)

    def test_wrong_product_promo_raises(self):
        user = _make_user("promo8", credit=500)
        promo = _make_promo(product=PromoCode.PRODUCT_RIDER_STATS)

        with self.assertRaises(ValueError, msg="nelze použít pro tento produkt"):
            purchase_mobile_app_subscription(user, promo_code_str=promo.code)

    def test_all_product_promo_works_for_mobile(self):
        user = _make_user("promo9", credit=500)
        promo = _make_promo(product=PromoCode.PRODUCT_ALL, discount_type=PromoCode.DISCOUNT_FREE)

        sub, created = purchase_mobile_app_subscription(user, promo_code_str=promo.code)
        self.assertTrue(created)

    def test_free_charge_creates_no_credit_deduction(self):
        """Při nulové ceně nevzniká žádný charge záznam."""
        self.season.mobile_app_annual_price = 0
        self.season.save()
        user = _make_user("free1", credit=0)

        sub, created = purchase_mobile_app_subscription(user)

        self.assertTrue(created)
        self.assertFalse(MobileAppCharge.objects.filter(user=user).exists())


# ===========================================================================
# 3. cancel / resume
# ===========================================================================

class CancelResumeMobileSubscriptionTests(TestCase):
    def setUp(self):
        _make_season()
        self.user = _make_user("canceluser", credit=500)
        self.sub, _ = purchase_mobile_app_subscription(self.user)

    def test_cancel_disables_auto_renew(self):
        cancel_mobile_app_subscription(self.sub)
        self.sub.refresh_from_db()

        self.assertFalse(self.sub.auto_renew)
        self.assertIsNotNone(self.sub.canceled_at)

    def test_cancel_keeps_active_status_until_expiry(self):
        cancel_mobile_app_subscription(self.sub)
        self.sub.refresh_from_db()

        self.assertEqual(self.sub.status, MobileAppSubscription.STATUS_ACTIVE)

    def test_cancel_expired_sets_canceled_status(self):
        self.sub.expires_at = timezone.now() - timedelta(seconds=1)
        self.sub.save()
        cancel_mobile_app_subscription(self.sub)
        self.sub.refresh_from_db()

        self.assertEqual(self.sub.status, MobileAppSubscription.STATUS_CANCELED)

    def test_resume_enables_auto_renew(self):
        cancel_mobile_app_subscription(self.sub)
        resume_mobile_app_subscription(self.sub)
        self.sub.refresh_from_db()

        self.assertTrue(self.sub.auto_renew)
        self.assertIsNone(self.sub.canceled_at)

    def test_has_active_access_after_cancel_before_expiry(self):
        cancel_mobile_app_subscription(self.sub)
        self.assertTrue(has_active_mobile_app_access(self.user))

    def test_no_active_access_after_expiry(self):
        self.sub.expires_at = timezone.now() - timedelta(seconds=1)
        self.sub.save()
        self.assertFalse(has_active_mobile_app_access(self.user))


# ===========================================================================
# 4. renew_due_mobile_app_subscriptions()
# ===========================================================================

class RenewMobileSubscriptionsTests(TestCase):
    def setUp(self):
        self.season = _make_season(price=499)

    def _expired_sub(self, user):
        sub, _ = purchase_mobile_app_subscription(user)
        sub.expires_at = timezone.now() - timedelta(seconds=1)
        sub.save()
        return sub

    def test_renews_due_subscription(self):
        user = _make_user("renew1", credit=1000)
        self._expired_sub(user)

        result = renew_due_mobile_app_subscriptions()

        self.assertEqual(result["renewed"], 1)
        sub = MobileAppSubscription.objects.get(user=user)
        self.assertEqual(sub.status, MobileAppSubscription.STATUS_ACTIVE)
        user.refresh_from_db()
        self.assertEqual(user.credit, 2)  # 1000 - 499 (initial) - 499 (renewal) = 2

    def test_insufficient_credit_sets_past_due(self):
        user = _make_user("renew2", credit=499)
        self._expired_sub(user)

        result = renew_due_mobile_app_subscriptions()

        self.assertEqual(result["failed"], 1)
        sub = MobileAppSubscription.objects.get(user=user)
        self.assertEqual(sub.status, MobileAppSubscription.STATUS_PAST_DUE)

    def test_auto_renew_off_skips_subscription(self):
        user = _make_user("renew3", credit=1000)
        sub = self._expired_sub(user)
        sub.auto_renew = False
        sub.save()

        result = renew_due_mobile_app_subscriptions()

        self.assertEqual(result["renewed"], 0)

    def test_renewal_creates_charge_with_renewal_reason(self):
        user = _make_user("renew4", credit=1000)
        self._expired_sub(user)

        renew_due_mobile_app_subscriptions()

        charges = MobileAppCharge.objects.filter(user=user).order_by("transaction_date")
        self.assertEqual(charges.count(), 2)
        self.assertEqual(charges.last().reason, MobileAppCharge.REASON_RENEWAL)

    def test_renewal_extends_by_365_days(self):
        user = _make_user("renew5", credit=1000)
        sub = self._expired_sub(user)
        old_expires = sub.expires_at

        renew_due_mobile_app_subscriptions()

        sub.refresh_from_db()
        delta = sub.expires_at - old_expires
        self.assertGreaterEqual(delta.days, 364)


# ===========================================================================
# 5. Výpočet kreditu zahrnuje MobileAppCharge
# ===========================================================================

class CreditBalanceWithMobileChargeTests(TestCase):
    def test_mobile_charge_reduces_balance(self):
        _make_season(price=499)
        user = _make_user("balance1", credit=600)

        purchase_mobile_app_subscription(user)

        balance = calculate_user_balance(user.pk)
        self.assertEqual(balance, 101)

    def test_invalid_charge_does_not_reduce_balance(self):
        _make_season(price=499)
        user = _make_user("balance2", credit=600)
        purchase_mobile_app_subscription(user)

        charge = MobileAppCharge.objects.get(user=user)
        charge.payment_valid = False
        charge.save()

        balance = calculate_user_balance(user.pk)
        self.assertEqual(balance, 600)


# ===========================================================================
# 6. Web view /rider/mobile-app-subscription
# ===========================================================================

class MobileAppSubscriptionViewTests(TestCase):
    def setUp(self):
        self.season = _make_season(price=499)
        self.url = reverse("user:subscription-mobile")

    def test_get_requires_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("next=", resp["Location"])

    def test_get_renders_for_logged_in_user(self):
        user = _make_user("webview1", credit=500)
        self.client.force_login(user)

        resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("annual_price", resp.context)
        self.assertEqual(resp.context["annual_price"], 499)

    def test_get_shows_active_subscription(self):
        user = _make_user("webview2", credit=500)
        purchase_mobile_app_subscription(user)
        self.client.force_login(user)

        resp = self.client.get(self.url)

        self.assertIsNotNone(resp.context["subscription"])

    def test_post_activate_creates_subscription(self):
        user = _make_user("webview3", credit=500)
        self.client.force_login(user)

        resp = self.client.post(self.url, {"action": "activate"})

        self.assertRedirects(resp, self.url)
        self.assertTrue(MobileAppSubscription.objects.filter(user=user).exists())

    def test_post_activate_with_free_promo(self):
        user = _make_user("webview4", credit=0)
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FREE)
        self.client.force_login(user)

        resp = self.client.post(self.url, {"action": "activate", "promo_code": promo.code})

        self.assertRedirects(resp, self.url)
        self.assertTrue(MobileAppSubscription.objects.filter(user=user, status="active").exists())

    def test_post_activate_insufficient_credit_shows_error(self):
        user = _make_user("webview5", credit=10)
        self.client.force_login(user)

        resp = self.client.post(self.url, {"action": "activate"}, follow=True)

        self.assertContains(resp, "Nedostatek")

    def test_post_cancel_disables_auto_renew(self):
        user = _make_user("webview6", credit=500)
        purchase_mobile_app_subscription(user)
        self.client.force_login(user)

        self.client.post(self.url, {"action": "cancel"})

        sub = MobileAppSubscription.objects.get(user=user)
        self.assertFalse(sub.auto_renew)

    def test_post_resume_enables_auto_renew(self):
        user = _make_user("webview7", credit=500)
        sub, _ = purchase_mobile_app_subscription(user)
        cancel_mobile_app_subscription(sub)
        self.client.force_login(user)

        self.client.post(self.url, {"action": "resume"})

        sub.refresh_from_db()
        self.assertTrue(sub.auto_renew)


# ===========================================================================
# 7. Admin view /rider/promo-codes
# ===========================================================================

class PromoCodesAdminViewTests(TestCase):
    def setUp(self):
        self.url = reverse("rider:promo-codes")
        self.staff = _make_user("adminpc", is_staff=True)
        self.regular = _make_user("regularpc")

    def test_requires_staff(self):
        self.client.force_login(self.regular)
        resp = self.client.get(self.url)
        self.assertNotEqual(resp.status_code, 200)

    def test_staff_can_access(self):
        self.client.force_login(self.staff)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_generate_creates_promo_code(self):
        self.client.force_login(self.staff)
        resp = self.client.post(self.url, {
            "action": "generate",
            "product": PromoCode.PRODUCT_MOBILE_APP,
            "discount_type": PromoCode.DISCOUNT_FREE,
            "discount_value": "100",
        })
        self.assertRedirects(resp, self.url)
        self.assertEqual(PromoCode.objects.count(), 1)

    def test_generate_with_max_uses(self):
        self.client.force_login(self.staff)
        self.client.post(self.url, {
            "action": "generate",
            "product": PromoCode.PRODUCT_MOBILE_APP,
            "discount_type": PromoCode.DISCOUNT_PERCENT,
            "discount_value": "50",
            "max_uses": "10",
        })
        promo = PromoCode.objects.get()
        self.assertEqual(promo.max_uses, 10)
        self.assertEqual(promo.discount_value, 50)

    def test_deactivate_promo(self):
        promo = _make_promo()
        self.client.force_login(self.staff)
        self.client.post(self.url, {"action": "deactivate", "promo_id": promo.pk})
        promo.refresh_from_db()
        self.assertFalse(promo.is_active)

    def test_activate_promo(self):
        promo = _make_promo(is_active=False)
        self.client.force_login(self.staff)
        self.client.post(self.url, {"action": "activate", "promo_id": promo.pk})
        promo.refresh_from_db()
        self.assertTrue(promo.is_active)

    def test_promo_list_shows_all_codes(self):
        _make_promo()
        _make_promo()
        self.client.force_login(self.staff)
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context["promo_codes"]), 2)


# ===========================================================================
# 8. API /api/subscriptions/mobile/
# ===========================================================================

class MobileSubscriptionAPITests(TestCase):
    def setUp(self):
        self.season = _make_season(price=499)
        self.client = APIClient()
        self.url = reverse("api:mobile-subscription")

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_get_unauthenticated_returns_401(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 401)

    def test_get_returns_price_and_no_subscription(self):
        user = _make_user("api1", credit=500)
        self._auth(user)

        resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data["subscription"])
        self.assertEqual(resp.data["price"], 499)
        self.assertEqual(resp.data["balance"], 500)

    def test_post_activates_subscription(self):
        user = _make_user("api2", credit=500)
        self._auth(user)

        resp = self.client.post(self.url)

        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["created"])
        self.assertEqual(resp.data["new_balance"], 1)

    def test_post_duplicate_returns_200_not_201(self):
        user = _make_user("api3", credit=1000)
        self._auth(user)

        self.client.post(self.url)
        resp = self.client.post(self.url)

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["created"])

    def test_post_insufficient_credit_returns_400(self):
        user = _make_user("api4", credit=10)
        self._auth(user)

        resp = self.client.post(self.url)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)

    def test_post_with_free_promo_activates_for_free(self):
        user = _make_user("api5", credit=0)
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FREE)
        self._auth(user)

        resp = self.client.post(self.url, {"promo_code": promo.code})

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["new_balance"], 0)

    def test_post_with_invalid_promo_returns_400(self):
        user = _make_user("api6", credit=500)
        self._auth(user)

        resp = self.client.post(self.url, {"promo_code": "INVALID99"})

        self.assertEqual(resp.status_code, 400)

    def test_delete_cancels_auto_renew(self):
        user = _make_user("api7", credit=500)
        purchase_mobile_app_subscription(user)
        self._auth(user)

        resp = self.client.delete(self.url)

        self.assertEqual(resp.status_code, 200)
        sub = MobileAppSubscription.objects.get(user=user)
        self.assertFalse(sub.auto_renew)

    def test_delete_without_subscription_returns_400(self):
        user = _make_user("api8")
        self._auth(user)

        resp = self.client.delete(self.url)

        self.assertEqual(resp.status_code, 400)

    def test_get_reflects_active_subscription(self):
        user = _make_user("api9", credit=500)
        purchase_mobile_app_subscription(user)
        self._auth(user)

        resp = self.client.get(self.url)

        self.assertIsNotNone(resp.data["subscription"])
        self.assertEqual(resp.data["subscription"]["status"], MobileAppSubscription.STATUS_ACTIVE)

    def test_me_endpoint_includes_mobile_subscription(self):
        user = _make_user("api10", credit=500)
        purchase_mobile_app_subscription(user)
        self._auth(user)

        resp = self.client.get(reverse("api:me"))

        self.assertEqual(resp.status_code, 200)
        self.assertIn("mobile_app_subscription", resp.data)
        self.assertTrue(resp.data["mobile_app_subscription"]["active"])

    def test_me_endpoint_no_subscription_returns_false(self):
        user = _make_user("api11")
        self._auth(user)

        resp = self.client.get(reverse("api:me"))

        self.assertFalse(resp.data["mobile_app_subscription"]["active"])
        self.assertIsNone(resp.data["mobile_app_subscription"]["expires_at"])


# ===========================================================================
# 9. API /api/promo-codes/validate/
# ===========================================================================

class PromoCodeValidateAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("api:promo-code-validate")

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_unauthenticated_returns_401(self):
        resp = self.client.post(self.url, {"code": "TEST"})
        self.assertEqual(resp.status_code, 401)

    def test_valid_code_returns_true(self):
        user = _make_user("val1")
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FREE)
        self._auth(user)

        resp = self.client.post(self.url, {"code": promo.code, "product": "mobile_app"})

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["valid"])
        self.assertEqual(resp.data["discount_type"], PromoCode.DISCOUNT_FREE)

    def test_nonexistent_code_returns_invalid(self):
        user = _make_user("val2")
        self._auth(user)

        resp = self.client.post(self.url, {"code": "NEEXISTUJE", "product": "mobile_app"})

        self.assertFalse(resp.data["valid"])

    def test_inactive_code_returns_invalid(self):
        user = _make_user("val3")
        promo = _make_promo(is_active=False)
        self._auth(user)

        resp = self.client.post(self.url, {"code": promo.code, "product": "mobile_app"})

        self.assertFalse(resp.data["valid"])

    def test_wrong_product_returns_invalid(self):
        user = _make_user("val4")
        promo = _make_promo(product=PromoCode.PRODUCT_RIDER_STATS)
        self._auth(user)

        resp = self.client.post(self.url, {"code": promo.code, "product": "mobile_app"})

        self.assertFalse(resp.data["valid"])

    def test_already_used_code_returns_invalid(self):
        _make_season(price=499)
        user = _make_user("val5", credit=0)
        promo = _make_promo(discount_type=PromoCode.DISCOUNT_FREE)
        purchase_mobile_app_subscription(user, promo_code_str=promo.code)
        self._auth(user)

        resp = self.client.post(self.url, {"code": promo.code, "product": "mobile_app"})

        self.assertFalse(resp.data["valid"])

    def test_all_product_code_valid_for_mobile(self):
        user = _make_user("val6")
        promo = _make_promo(product=PromoCode.PRODUCT_ALL)
        self._auth(user)

        resp = self.client.post(self.url, {"code": promo.code, "product": "mobile_app"})

        self.assertTrue(resp.data["valid"])
