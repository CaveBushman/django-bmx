from datetime import date, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from club.models import Club
from event.models import CreditTransaction
from event.models_events import EntryClasses, Event
from eshop.cart import CART_SESSION_KEY
from eshop.invoice import generate_credit_note, generate_invoice
from eshop.models import (
    Category,
    FlexiExportSettings,
    Order,
    OrderHistory,
    Product,
    ProductVariant,
    StockAlertRequest,
    StockMovement,
    StockReservation,
)


class EshopCheckoutTemplateTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.category = Category.objects.create(name="Dresy", slug="dresy")
        self.product = Product.objects.create(
            category=self.category,
            name="Race Jersey",
            slug="race-jersey",
            active=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            label="L",
            price=1190,
            stock=5,
            active=True,
        )
        self.club = Club.objects.create(team_name="Test Club")
        self.entry_classes = EntryClasses.objects.create(
            event_name="Test classes",
            beginners_1="Beginners 1",
            beginners_2="Beginners 2",
            beginners_3="Beginners 3",
            beginners_4="Beginners 4",
            boys_6="Boys 6",
            girls_6="Girls 6",
            cr_boys_12_and_under="Boys 12 and under",
        )
        self.event = Event.objects.create(
            name="Test race",
            date=date.today() + timedelta(days=30),
            organizer=self.club,
            classes_and_fees_like=self.entry_classes,
            reg_open=True,
            reg_open_from=timezone.now() - timedelta(days=1),
            reg_open_to=timezone.now() + timedelta(days=1),
            type_for_ranking="Volný závod",
            eshop_pickup_enabled=True,
        )

    def test_checkout_warns_when_credit_is_insufficient(self):
        user = self.user_model.objects.create_user(
            first_name="Low",
            last_name="Credit",
            username="credit-low",
            email="credit-low@example.com",
            password="StrongPass123!",
        )
        user.credit = 100
        user.is_active = True
        user.save(update_fields=["credit", "is_active"])
        self.client.force_login(user)
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 2}
        session.save()

        response = self.client.get(reverse("eshop:checkout"))

        self.assertContains(response, "Nedostatečný kredit")
        self.assertContains(response, "Zpět do e-shopu")
        self.assertContains(response, 'disabled aria-disabled="true"', html=False)

    def test_checkout_does_not_create_order_when_credit_is_insufficient(self):
        user = self.user_model.objects.create_user(
            username="credit-low-post",
            email="credit-low-post@example.com",
            password="StrongPass123!",
            first_name="Low",
            last_name="Credit",
        )
        user.credit = 100
        user.is_active = True
        user.save(update_fields=["credit", "is_active"])
        self.client.force_login(user)
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 2}
        session.save()

        response = self.client.post(
            reverse("eshop:checkout"),
            {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone": "+420123456789",
                "event": self.event.pk,
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(response, "Nedostatečný kredit")

    def test_checkout_creates_paid_order_and_deducts_credit_immediately(self):
        user = self.user_model.objects.create_user(
            username="credit-ok-post",
            email="credit-ok@example.com",
            password="StrongPass123!",
            first_name="Ready",
            last_name="Buyer",
        )
        user.is_active = True
        user.save(update_fields=["is_active"])
        CreditTransaction.objects.create(
            user=user,
            amount=3000,
            kind=CreditTransaction.Kind.TOPUP,
            payment_complete=True,
        )
        self.client.force_login(user)
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 2}
        session.save()

        response = self.client.post(
            reverse("eshop:checkout"),
            {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone": "+420123456789",
                "event": self.event.pk,
                "note": "Predani na zavode",
            },
        )

        order = Order.objects.get()
        self.assertRedirects(response, reverse("eshop:order-confirmation", args=[order.pk]))
        order.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(order.credits_charged, 2380)
        self.assertEqual(user.credit, 620)
        self.assertTrue(
            CreditTransaction.objects.filter(
                user=user,
                amount=-2380,
                kind=CreditTransaction.Kind.ESHOP_PURCHASE,
                payment_complete=True,
            ).exists()
        )
        self.assertTrue(order.history.filter(action=OrderHistory.Action.CREATED).exists())
        self.assertTrue(order.history.filter(action=OrderHistory.Action.CREDIT_CHARGED).exists())
        self.assertTrue(order.history.filter(action=OrderHistory.Action.CONFIRMED).exists())
        self.assertTrue(order.history.filter(action=OrderHistory.Action.INVOICE_ISSUED).exists())
        movement = StockMovement.objects.get(order=order)
        self.assertEqual(movement.variant, self.variant)
        self.assertEqual(movement.movement_type, StockMovement.MovementType.ORDER_DECREMENT)
        self.assertEqual(movement.quantity_delta, -2)
        self.assertEqual(movement.stock_after, 3)

    def test_order_confirmation_is_final_confirmation_without_credit_payment_cta(self):
        user = self.user_model.objects.create_user(
            username="confirmation-user",
            email="confirmation@example.com",
            password="StrongPass123!",
            first_name="Final",
            last_name="Buyer",
        )
        user.is_active = True
        user.save(update_fields=["is_active"])
        CreditTransaction.objects.create(
            user=user,
            amount=5000,
            kind=CreditTransaction.Kind.TOPUP,
            payment_complete=True,
        )

        order = Order.objects.create(
            user=user,
            first_name="Final",
            last_name="Buyer",
            email=user.email,
            event=self.event,
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)

        session = self.client.session
        session["last_order_id"] = order.pk
        session.save()
        self.client.force_login(user)

        response = self.client.get(reverse("eshop:order-confirmation", args=[order.pk]))

        self.assertContains(response, "Objednávka potvrzena")
        self.assertContains(response, "Kredit odečten automaticky")
        self.assertNotContains(response, "Zaplatit kredity")
        self.assertNotContains(response, "Zaplatit 1190 Kč")

    def test_eshop_invoice_uses_pdf_generator_successfully(self):
        user = self.user_model.objects.create_user(
            username="invoice-user",
            email="invoice@example.com",
            password="StrongPass123!",
            first_name="Invoice",
            last_name="Buyer",
        )
        order = Order.objects.create(
            user=user,
            first_name="Invoice",
            last_name="Buyer",
            email=user.email,
            event=self.event,
            phone="+420123456789",
            note="Predat na zavode",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)

        pdf_buffer = generate_invoice(order)

        self.assertTrue(pdf_buffer.getvalue().startswith(b"%PDF"))

    def test_eshop_invoice_number_is_generated_once_in_own_series(self):
        user = self.user_model.objects.create_user(
            username="invoice-number-user",
            email="invoice-number@example.com",
            password="StrongPass123!",
            first_name="Invoice",
            last_name="Number",
        )
        order = Order.objects.create(
            user=user,
            first_name="Invoice",
            last_name="Number",
            email=user.email,
            event=self.event,
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)

        first_pdf = generate_invoice(order)
        order.refresh_from_db()
        first_number = order.invoice_number
        second_pdf = generate_invoice(order)
        order.refresh_from_db()

        self.assertTrue(first_pdf.getvalue().startswith(b"%PDF"))
        self.assertTrue(second_pdf.getvalue().startswith(b"%PDF"))
        self.assertRegex(first_number, r"^003\d{4}\d{2}\d{3}$")
        self.assertEqual(order.invoice_number, first_number)

    def test_eshop_credit_note_uses_existing_invoice_number(self):
        user = self.user_model.objects.create_user(
            username="credit-note-user",
            email="credit-note@example.com",
            password="StrongPass123!",
            first_name="Credit",
            last_name="Note",
        )
        order = Order.objects.create(
            user=user,
            first_name="Credit",
            last_name="Note",
            email=user.email,
            event=self.event,
            invoice_number="003202604001",
            status=Order.Status.CANCELED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)

        pdf_buffer = generate_credit_note(order)
        order.refresh_from_db()

        self.assertTrue(pdf_buffer.getvalue().startswith(b"%PDF"))
        self.assertEqual(order.credit_note_number, "003202604001-D")

    def test_checkout_uses_credit_checkout_layout(self):
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 2}
        session.save()

        response = self.client.get(reverse("eshop:checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dokončení objednávky")
        self.assertContains(response, "Úhrada kredity")
        self.assertContains(response, "Kredity z účtu")
        self.assertContains(response, "Souhrn objednávky")
        self.assertNotContains(response, "Číslo karty")
        self.assertNotContains(response, "PayPal")

    def test_checkout_offers_only_events_enabled_for_eshop_pickup(self):
        disabled_event = Event.objects.create(
            name="No pickup race",
            date=date.today() + timedelta(days=35),
            organizer=self.club,
            classes_and_fees_like=self.entry_classes,
            reg_open=True,
            type_for_ranking="Volný závod",
            eshop_pickup_enabled=False,
        )
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 1}
        session.save()

        response = self.client.get(reverse("eshop:checkout"))

        self.assertContains(response, self.event.name)
        self.assertNotContains(response, disabled_event.name)

    def test_checkout_shows_selected_pickup_event_details(self):
        self.event.eshop_pickup_location = "Stan e-shopu u registrace"
        self.event.eshop_pickup_time = "Sobota 9:00-12:00"
        self.event.eshop_pickup_note = "Připrav si číslo faktury."
        self.event.save(update_fields=["eshop_pickup_location", "eshop_pickup_time", "eshop_pickup_note"])
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 1}
        session.save()

        response = self.client.get(reverse("eshop:checkout"))

        self.assertContains(response, "Informace k výdeji")
        self.assertContains(response, "Stan e-shopu u registrace")
        self.assertContains(response, "Sobota 9:00-12:00")
        self.assertContains(response, "Připrav si číslo faktury.")

    def test_checkout_is_disabled_when_no_pickup_event_is_available(self):
        self.event.eshop_pickup_enabled = False
        self.event.save(update_fields=["eshop_pickup_enabled"])
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 1}
        session.save()

        response = self.client.get(reverse("eshop:checkout"))

        self.assertContains(response, "Není dostupné místo výdeje")
        self.assertContains(response, "Aktuálně není vypsané místo výdeje")
        self.assertContains(response, 'disabled aria-disabled="true"', html=False)

    def test_product_pages_render_extended_product_structure(self):
        self.product.collection = "National Team"
        self.product.subtitle = "Závodní dres pro český tým"
        self.product.material = "Prodyšný polyester"
        self.product.fit_note = "Užší race fit"
        self.product.pickup_note = "Předání na vybraném závodě"
        self.variant.stock = 2
        self.category.slug = "obleceni"
        self.product.save(
            update_fields=[
                "collection",
                "subtitle",
                "material",
                "fit_note",
                "pickup_note",
            ]
        )
        self.variant.save(update_fields=["stock"])
        self.category.save(update_fields=["slug"])

        shop_response = self.client.get(reverse("eshop:shop"))
        detail_response = self.client.get(reverse("eshop:product-detail", args=[self.product.slug]))

        self.assertContains(shop_response, "National Team")
        self.assertContains(shop_response, "Závodní dres pro český tým")
        self.assertContains(shop_response, "Materiál")
        self.assertContains(shop_response, "Užší race fit")
        self.assertContains(detail_response, "National Team")
        self.assertContains(detail_response, "Prodyšný polyester")
        self.assertContains(detail_response, "Předání na vybraném závodě")
        self.assertContains(detail_response, "Poslední kusy skladem")
        self.assertContains(detail_response, "Otevřít tabulku velikostí")

    def test_product_detail_marks_sold_out_variant_and_exposes_variant_stock(self):
        sold_out_variant = ProductVariant.objects.create(
            product=self.product,
            label="XL",
            price=1190,
            stock=0,
            active=True,
            sort_order=2,
        )

        response = self.client.get(reverse("eshop:product-detail", args=[self.product.slug]))

        self.assertContains(response, f'data-variant-id="{self.variant.pk}"', html=False)
        self.assertContains(response, 'data-stock="5"', html=False)
        self.assertContains(response, f'data-variant-id="{sold_out_variant.pk}"', html=False)
        self.assertContains(response, 'data-variant-label="XL"', html=False)
        self.assertContains(response, "Vyprodáno")

    def test_product_detail_shows_stock_alert_form_for_sold_out_variant(self):
        ProductVariant.objects.create(
            product=self.product,
            label="XL",
            price=1190,
            stock=0,
            active=True,
            sort_order=2,
        )

        response = self.client.get(reverse("eshop:product-detail", args=[self.product.slug]))

        self.assertContains(response, "Hlídat dostupnost")
        self.assertContains(response, "stock-alert-modal")
        self.assertNotContains(response, "Hlídat vyprodanou velikost")
        self.assertContains(response, "Uložit požadavek")
        self.assertContains(response, "XL")

    def test_user_can_request_stock_alert_for_sold_out_variant(self):
        sold_out_variant = ProductVariant.objects.create(
            product=self.product,
            label="XL",
            price=1190,
            stock=0,
            active=True,
            sort_order=2,
        )
        user = self.user_model.objects.create_user(
            username="stock-alert-user",
            email="stock-alert@example.com",
            password="StrongPass123!",
            first_name="Stock",
            last_name="Alert",
        )
        user.is_active = True
        user.save(update_fields=["is_active"])
        self.client.force_login(user)

        response = self.client.post(
            reverse("eshop:request-stock-alert", args=[self.product.slug]),
            {
                "variant": sold_out_variant.pk,
                "email": "Stock-Alert@Example.com",
                "note": "Zajem o dva kusy",
            },
            follow=True,
        )

        request_obj = StockAlertRequest.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request_obj.variant, sold_out_variant)
        self.assertEqual(request_obj.user, user)
        self.assertEqual(request_obj.email, "stock-alert@example.com")
        self.assertEqual(request_obj.note, "Zajem o dva kusy")
        self.assertContains(response, "Požadavek na naskladnění je uložený")

    def test_stock_alert_request_does_not_duplicate_open_request(self):
        sold_out_variant = ProductVariant.objects.create(
            product=self.product,
            label="XL",
            price=1190,
            stock=0,
            active=True,
            sort_order=2,
        )
        StockAlertRequest.objects.create(
            variant=sold_out_variant,
            email="duplicate@example.com",
        )

        response = self.client.post(
            reverse("eshop:request-stock-alert", args=[self.product.slug]),
            {
                "variant": sold_out_variant.pk,
                "email": "DUPLICATE@example.com",
                "note": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StockAlertRequest.objects.count(), 1)
        self.assertContains(response, "Tento požadavek už evidujeme")

    def test_checkout_can_update_item_quantity(self):
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 1}
        session.save()

        response = self.client.post(
            reverse("eshop:checkout"),
            {
                "action": "update",
                "variant_id": self.variant.pk,
                "quantity": 3,
            },
        )

        self.assertRedirects(response, reverse("eshop:checkout"))
        self.assertEqual(self.client.session[CART_SESSION_KEY][str(self.variant.pk)], 3)

    def test_checkout_can_remove_item(self):
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 1}
        session.save()

        response = self.client.post(
            reverse("eshop:checkout"),
            {
                "action": "remove",
                "variant_id": self.variant.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("eshop:checkout"))
        self.assertNotIn(str(self.variant.pk), self.client.session[CART_SESSION_KEY])

    def test_add_to_cart_redirects_directly_to_checkout(self):
        response = self.client.post(
            reverse("eshop:add-to-cart"),
            {"variant_id": self.variant.pk},
        )

        self.assertRedirects(response, reverse("eshop:checkout"))

    def test_add_to_cart_does_not_exceed_available_stock(self):
        self.variant.stock = 1
        self.variant.save(update_fields=["stock"])

        first = self.client.post(reverse("eshop:add-to-cart"), {"variant_id": self.variant.pk})
        second = self.client.post(reverse("eshop:add-to-cart"), {"variant_id": self.variant.pk})

        self.assertRedirects(first, reverse("eshop:checkout"))
        self.assertRedirects(second, reverse("eshop:checkout"))
        self.assertEqual(self.client.session[CART_SESSION_KEY][str(self.variant.pk)], 1)

    def test_cart_route_redirects_to_checkout_when_items_exist(self):
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 1}
        session.save()

        response = self.client.get(reverse("eshop:cart"))

        self.assertRedirects(response, reverse("eshop:checkout"))

    def test_checkout_adjusts_quantity_when_stock_drops(self):
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 4}
        session.save()
        self.variant.stock = 2
        self.variant.save(update_fields=["stock"])

        response = self.client.get(reverse("eshop:checkout"), follow=True)

        self.assertContains(response, "upraven na aktuálně dostupné množství po započtení rezervací")
        self.assertEqual(self.client.session[CART_SESSION_KEY][str(self.variant.pk)], 2)

    def test_checkout_creates_stock_reservation_for_current_session(self):
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 2}
        session.save()

        response = self.client.get(reverse("eshop:checkout"))

        reservation = StockReservation.objects.get(session_key=self.client.session.session_key, variant=self.variant)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(reservation.quantity, 2)
        self.assertGreater(reservation.expires_at, timezone.now())
        self.assertContains(response, "Kusy v checkoutu držíme rezervované")

    def test_checkout_respects_stock_reservation_from_another_session(self):
        other_client = Client()
        other_session = other_client.session
        other_session.save()
        StockReservation.objects.create(
            session_key=other_session.session_key,
            variant=self.variant,
            quantity=4,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 2}
        session.save()

        response = self.client.get(reverse("eshop:checkout"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[CART_SESSION_KEY][str(self.variant.pk)], 1)
        self.assertContains(response, "upraven na aktuálně dostupné množství po započtení rezervací")

    def test_checkout_deducts_product_stock_after_successful_order(self):
        user = self.user_model.objects.create_user(
            username="stock-ok-post",
            email="stock-ok@example.com",
            password="StrongPass123!",
            first_name="Stock",
            last_name="Buyer",
        )
        user.is_active = True
        user.save(update_fields=["is_active"])
        CreditTransaction.objects.create(
            user=user,
            amount=3000,
            kind=CreditTransaction.Kind.TOPUP,
            payment_complete=True,
        )
        session = self.client.session
        session[CART_SESSION_KEY] = {str(self.variant.pk): 2}
        session.save()
        self.client.force_login(user)

        response = self.client.post(
            reverse("eshop:checkout"),
            {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone": "+420123456789",
                "event": self.event.pk,
                "note": "",
            },
        )

        order = Order.objects.get()
        self.assertRedirects(response, reverse("eshop:order-confirmation", args=[order.pk]))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)
        self.assertTrue(
            StockMovement.objects.filter(
                order=order,
                variant=self.variant,
                movement_type=StockMovement.MovementType.ORDER_DECREMENT,
                quantity_delta=-2,
                stock_after=3,
            ).exists()
        )
        self.assertFalse(
            StockReservation.objects.filter(
                session_key=self.client.session.session_key,
                variant=self.variant,
            ).exists()
        )

    def test_user_can_cancel_order_and_get_credit_and_stock_back(self):
        user = self.user_model.objects.create_user(
            username="cancel-user",
            email="cancel@example.com",
            password="StrongPass123!",
            first_name="Cancel",
            last_name="Buyer",
        )
        user.is_active = True
        user.save(update_fields=["is_active"])
        order = Order.objects.create(
            user=user,
            first_name="Cancel",
            last_name="Buyer",
            email=user.email,
            event=self.event,
            credits_charged=2380,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=2, unit_price=self.variant.price)
        self.variant.stock = 3
        self.variant.save(update_fields=["stock"])
        CreditTransaction.objects.create(
            user=user,
            amount=2480,
            kind=CreditTransaction.Kind.TOPUP,
            payment_complete=True,
        )
        CreditTransaction.objects.create(
            user=user,
            amount=-2380,
            kind=CreditTransaction.Kind.ESHOP_PURCHASE,
            payment_complete=True,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("eshop:cancel-order", args=[order.pk]), follow=True)

        order.refresh_from_db()
        user.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, Order.Status.CANCELED)
        self.assertIsNone(order.credits_charged)
        self.assertEqual(user.credit, 2480)
        self.assertEqual(self.variant.stock, 5)
        self.assertTrue(
            StockMovement.objects.filter(
                order=order,
                variant=self.variant,
                movement_type=StockMovement.MovementType.CANCEL_RETURN,
                quantity_delta=2,
                stock_after=5,
            ).exists()
        )
        self.assertTrue(
            CreditTransaction.objects.filter(
                user=user,
                amount=2380,
                kind=CreditTransaction.Kind.ESHOP_REFUND,
                payment_complete=True,
            ).exists()
        )
        self.assertEqual(order.credit_note_number, f"{order.invoice_number}-D")
        self.assertTrue(bool(order.credit_note_pdf))
        self.assertContains(response, "byla stornována")

    def test_user_cannot_cancel_delivered_order(self):
        user = self.user_model.objects.create_user(
            username="delivered-user",
            email="delivered@example.com",
            password="StrongPass123!",
            first_name="Delivered",
            last_name="Buyer",
        )
        user.is_active = True
        user.save(update_fields=["is_active"])
        CreditTransaction.objects.create(
            user=user,
            amount=100,
            kind=CreditTransaction.Kind.TOPUP,
            payment_complete=True,
        )
        order = Order.objects.create(
            user=user,
            first_name="Delivered",
            last_name="Buyer",
            email=user.email,
            event=self.event,
            credits_charged=1190,
            status=Order.Status.DELIVERED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)
        self.client.force_login(user)

        response = self.client.post(reverse("eshop:cancel-order", args=[order.pk]), follow=True)

        order.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertEqual(user.credit, 100)
        self.assertContains(response, "už nelze stornovat")

    def test_my_orders_uses_custom_cancel_modal_instead_of_browser_confirm(self):
        user = self.user_model.objects.create_user(
            username="modal-cancel-user",
            email="modal-cancel@example.com",
            password="StrongPass123!",
            first_name="Modal",
            last_name="Cancel",
        )
        user.is_active = True
        user.save(update_fields=["is_active"])
        order = Order.objects.create(
            user=user,
            first_name="Modal",
            last_name="Cancel",
            email=user.email,
            event=self.event,
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)
        self.client.force_login(user)

        response = self.client.get(reverse("eshop:my-orders"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cancel-order-modal")
        self.assertContains(response, "data-cancel-order-open", html=False)
        self.assertContains(response, "Ano, stornovat")
        self.assertNotContains(response, "confirm(")

    def test_staff_can_export_pickup_orders_csv(self):
        staff = self.user_model.objects.create_user(
            username="staff-export",
            email="staff-export@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Export",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        order = Order.objects.create(
            user=staff,
            first_name="Staff",
            last_name="Export",
            email=staff.email,
            event=self.event,
            invoice_number="003202604001",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=2, unit_price=self.variant.price)
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:pickup-export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("003202604001", response.content.decode("utf-8"))
        self.assertIn("Race Jersey / L x 2", response.content.decode("utf-8"))

    def test_staff_can_export_accounting_orders_csv(self):
        staff = self.user_model.objects.create_user(
            username="staff-accounting-export",
            email="staff-accounting-export@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Accounting",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        confirmed_order = Order.objects.create(
            user=staff,
            first_name="Staff",
            last_name="Accounting",
            email=staff.email,
            event=self.event,
            invoice_number="003202604008",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        confirmed_order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)
        canceled_order = Order.objects.create(
            user=staff,
            first_name="Staff",
            last_name="Refund",
            email=staff.email,
            event=self.event,
            invoice_number="003202604009",
            credit_note_number="003202604009-D",
            status=Order.Status.CANCELED,
        )
        canceled_order.items.create(variant=self.variant, quantity=2, unit_price=self.variant.price)
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:accounting-export"))

        content = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Faktura;003202604008", content)
        self.assertIn("Dobropis;003202604009-D", content)
        self.assertIn("1190", content)

    def test_staff_can_export_abra_flexi_xml(self):
        staff = self.user_model.objects.create_user(
            username="staff-flexi-export",
            email="staff-flexi-export@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Flexi",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        confirmed_order = Order.objects.create(
            user=staff,
            first_name="Staff",
            last_name="Flexi",
            email=staff.email,
            phone="+420123456789",
            event=self.event,
            invoice_number="003202604011",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        confirmed_order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)
        canceled_order = Order.objects.create(
            user=staff,
            first_name="Staff",
            last_name="RefundFlexi",
            email=staff.email,
            phone="+420123456789",
            event=self.event,
            invoice_number="003202604012",
            credit_note_number="003202604012-D",
            status=Order.Status.CANCELED,
        )
        canceled_order.items.create(variant=self.variant, quantity=2, unit_price=self.variant.price)
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:flexi-export"))

        content = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        self.assertIn("<winstrom version=\"1.0\">", content)
        self.assertIn("<typDokl>code:FAKTURA</typDokl>", content)
        self.assertIn("<typDokl>code:DOBROPIS</typDokl>", content)
        self.assertIn("<kod>003202604011</kod>", content)
        self.assertIn("<dobropisovanyDokl>code:003202604012</dobropisovanyDokl>", content)
        self.assertIn("<typSzbDphK>typSzbDph.dphOsv</typSzbDphK>", content)

    def test_flexi_export_uses_configured_codes(self):
        settings = FlexiExportSettings.get_solo()
        settings.invoice_document_type = "ESHOP-FA"
        settings.credit_note_document_type = "ESHOP-DOB"
        settings.center_code = "BMX"
        settings.payment_method_code = "KREDIT"
        settings.vat_classification_code = "osv"
        settings.save()
        staff = self.user_model.objects.create_user(
            username="staff-flexi-config",
            email="staff-flexi-config@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="FlexiConfig",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        order = Order.objects.create(
            user=staff,
            first_name="Staff",
            last_name="FlexiConfig",
            email=staff.email,
            phone="+420123456789",
            event=self.event,
            invoice_number="003202604013",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:flexi-export"))

        content = response.content.decode("utf-8")
        self.assertIn("<typDokl>code:ESHOP-FA</typDokl>", content)
        self.assertIn("<stredisko>code:BMX</stredisko>", content)
        self.assertIn("<formaUhradyCis>code:KREDIT</formaUhradyCis>", content)
        self.assertIn("<clenDph>osv</clenDph>", content)

    def test_staff_can_open_pickup_print_view(self):
        staff = self.user_model.objects.create_user(
            username="staff-pickup-print",
            email="staff-pickup-print@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Print",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        order = Order.objects.create(
            user=staff,
            first_name="Print",
            last_name="Buyer",
            email=staff.email,
            event=self.event,
            invoice_number="003202604010",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=2, unit_price=self.variant.price)
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:pickup-print"), {"event": self.event.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Výdejový list")
        self.assertContains(response, "003202604010")
        self.assertContains(response, "Počet kusů: 2")
        self.assertContains(response, "Převzato / podpis")

    def test_staff_can_mark_pickup_order_delivered_from_dashboard(self):
        staff = self.user_model.objects.create_user(
            username="staff-pickup",
            email="staff-pickup@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Pickup",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        order = Order.objects.create(
            user=staff,
            first_name="Pickup",
            last_name="Buyer",
            email=staff.email,
            event=self.event,
            invoice_number="003202604002",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)
        self.client.force_login(staff)

        response = self.client.post(
            reverse("eshop:pickup-delivered", args=[order.pk]),
            {"pickup_event": str(self.event.pk)},
            follow=True,
        )

        order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertIsNotNone(order.delivered_at)
        self.assertEqual(order.delivered_by, staff)
        self.assertContains(response, "byla označena jako předaná")

    def test_staff_can_mark_pickup_order_shipped_from_dashboard(self):
        staff = self.user_model.objects.create_user(
            username="staff-shipped",
            email="staff-shipped@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Shipped",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        order = Order.objects.create(
            user=staff,
            first_name="Shipped",
            last_name="Buyer",
            email=staff.email,
            event=self.event,
            invoice_number="003202604003",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)
        self.client.force_login(staff)

        response = self.client.post(
            reverse("eshop:pickup-shipped", args=[order.pk]),
            {"pickup_event": str(self.event.pk)},
            follow=True,
        )

        order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, Order.Status.SHIPPED)
        self.assertIsNone(order.delivered_at)
        self.assertContains(response, "byla označena jako odeslaná")

    def test_pickup_dashboard_shows_delivered_today_summary(self):
        staff = self.user_model.objects.create_user(
            username="staff-delivered-today",
            email="staff-delivered-today@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Today",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        delivered_order = Order.objects.create(
            user=staff,
            first_name="Today",
            last_name="Buyer",
            email=staff.email,
            event=self.event,
            invoice_number="003202604004",
            credits_charged=1190,
            status=Order.Status.DELIVERED,
            delivered_at=timezone.now(),
            delivered_by=staff,
        )
        delivered_order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Předané dnes")
        self.assertContains(response, "003202604004")
        self.assertContains(response, "předáno dnes")

    def test_pickup_dashboard_shows_total_pieces_for_selected_event(self):
        staff = self.user_model.objects.create_user(
            username="staff-pieces",
            email="staff-pieces@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Pieces",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        order_one = Order.objects.create(
            user=staff,
            first_name="Pieces",
            last_name="One",
            email=staff.email,
            event=self.event,
            invoice_number="003202604005",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order_one.items.create(variant=self.variant, quantity=2, unit_price=self.variant.price)
        order_two = Order.objects.create(
            user=staff,
            first_name="Pieces",
            last_name="Two",
            email=staff.email,
            event=self.event,
            invoice_number="003202604006",
            credit_note_number="TMP-PIECES-006",
            credits_charged=1190,
            status=Order.Status.SHIPPED,
        )
        order_two.items.create(variant=self.variant, quantity=3, unit_price=self.variant.price)
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:index"), {"pickup_event": str(self.event.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "objednávek")
        self.assertContains(response, "kusů k výdeji")

    def test_pickup_dashboard_ignores_orders_for_events_without_eshop_pickup(self):
        staff = self.user_model.objects.create_user(
            username="staff-disabled-pickup",
            email="staff-disabled-pickup@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="DisabledPickup",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        disabled_event = Event.objects.create(
            name="Disabled pickup race",
            date=date.today() + timedelta(days=40),
            organizer=self.club,
            classes_and_fees_like=self.entry_classes,
            reg_open=True,
            type_for_ranking="Volný závod",
            eshop_pickup_enabled=False,
        )
        order = Order.objects.create(
            user=staff,
            first_name="Disabled",
            last_name="Pickup",
            email=staff.email,
            event=disabled_event,
            invoice_number="003202604099",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:index"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Disabled pickup race")
        self.assertNotContains(response, "003202604099")

    def test_pickup_dashboard_shows_active_stock_reservations_audit(self):
        staff = self.user_model.objects.create_user(
            username="staff-reservations",
            email="staff-reservations@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Reservations",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        StockReservation.objects.create(
            session_key="reservation-session-1234",
            variant=self.variant,
            quantity=2,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aktivní rezervace skladu")
        self.assertContains(response, "relací")
        self.assertContains(response, "blokovaných kusů")
        self.assertContains(response, "Race Jersey")
        self.assertContains(response, "Velikost: L")
        self.assertContains(response, "…ion-1234")

    def test_eshop_admin_index_shows_open_stock_alert_requests(self):
        staff = self.user_model.objects.create_user(
            username="staff-stock-alerts",
            email="staff-stock-alerts@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Alerts",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        sold_out_variant = ProductVariant.objects.create(
            product=self.product,
            label="XL",
            price=1190,
            stock=0,
            active=True,
            sort_order=2,
        )
        StockAlertRequest.objects.create(
            variant=sold_out_variant,
            email="rider@example.com",
            note="Chci jeden kus na zavod.",
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Poptávka po naskladnění")
        self.assertContains(response, "Nejžádanější varianty")
        self.assertContains(response, "Race Jersey")
        self.assertContains(response, "Velikost: XL")
        self.assertContains(response, "rider@example.com")
        self.assertContains(response, "Chci jeden kus na zavod.")

    def test_django_admin_stock_alert_request_changelist_renders(self):
        staff = self.user_model.objects.create_user(
            username="stock-alert-admin",
            email="stock-alert-admin@example.com",
            password="StrongPass123!",
            first_name="Stock",
            last_name="Admin",
        )
        staff.is_staff = True
        staff.is_superuser = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_superuser", "is_active"])
        sold_out_variant = ProductVariant.objects.create(
            product=self.product,
            label="XL",
            price=1190,
            stock=0,
            active=True,
            sort_order=2,
        )
        StockAlertRequest.objects.create(
            variant=sold_out_variant,
            email="rider@example.com",
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("admin:eshop_stockalertrequest_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Otevřeno")
        self.assertContains(response, "rider@example.com")

    def test_eshop_admin_index_cleans_expired_stock_reservations(self):
        staff = self.user_model.objects.create_user(
            username="staff-clean-reservations",
            email="staff-clean-reservations@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Clean",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        expired = StockReservation.objects.create(
            session_key="expired-session",
            variant=self.variant,
            quantity=2,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        active = StockReservation.objects.create(
            session_key="active-session",
            variant=self.variant,
            quantity=1,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:index"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(StockReservation.objects.filter(pk=expired.pk).exists())
        self.assertTrue(StockReservation.objects.filter(pk=active.pk).exists())
        self.assertContains(response, "odstraněna 1 expirovaná rezervace")

    def test_cleanup_stock_reservations_command_deletes_only_expired_rows(self):
        expired = StockReservation.objects.create(
            session_key="expired-command-session",
            variant=self.variant,
            quantity=2,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        active = StockReservation.objects.create(
            session_key="active-command-session",
            variant=self.variant,
            quantity=1,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        output = StringIO()

        call_command("cleanup_stock_reservations", stdout=output)

        self.assertFalse(StockReservation.objects.filter(pk=expired.pk).exists())
        self.assertTrue(StockReservation.objects.filter(pk=active.pk).exists())
        self.assertIn("Smazáno expirovaných rezervací: 1", output.getvalue())

    def test_staff_can_open_custom_admin_order_detail(self):
        staff = self.user_model.objects.create_user(
            username="staff-order-detail",
            email="staff-order-detail@example.com",
            password="StrongPass123!",
            first_name="Staff",
            last_name="Detail",
        )
        staff.is_staff = True
        staff.is_active = True
        staff.save(update_fields=["is_staff", "is_active"])
        order = Order.objects.create(
            user=staff,
            first_name="Detail",
            last_name="Buyer",
            email=staff.email,
            phone="+420123456789",
            event=self.event,
            invoice_number="003202604007",
            internal_note="Připravit k výdeji u registrace.",
            credits_charged=1190,
            status=Order.Status.CONFIRMED,
        )
        order.items.create(variant=self.variant, quantity=1, unit_price=self.variant.price)
        CreditTransaction.objects.create(
            user=staff,
            amount=-1190,
            kind=CreditTransaction.Kind.ESHOP_PURCHASE,
            transaction_id=f"eshop-order-{order.pk}",
            payment_complete=True,
        )
        OrderHistory.record(
            order=order,
            action=OrderHistory.Action.INVOICE_ISSUED,
            actor=staff,
            note="Faktura 003202604007",
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("eshop:admin-order-detail", args=[order.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "003202604007")
        self.assertContains(response, "Připravit k výdeji u registrace.")
        self.assertContains(response, "Kreditní transakce")
        self.assertContains(response, "Historie objednávky")
        self.assertContains(response, "Faktura 003202604007")
        self.assertContains(response, "Race Jersey")
