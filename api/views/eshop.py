"""Mobilní API katalogu, košíku a e-shop checkoutu.

Klientské ceny a dostupnost jsou pouze informativní; při vytvoření objednávky se
vždy znovu ověřují a sklad se mění atomicky na serveru. Platí se kartou přes
Stripe Checkout — checkout vrací ``checkout_url``, kterou klient otevře.
"""

from datetime import timedelta

from django.db import transaction as db_tx
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status, filters, serializers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer

from event.models_events import Event as EventModel
from eshop.models import Category, Product, ProductVariant, Order, OrderItem, OrderHistory
from eshop.serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    OrderSerializer,
)
from eshop.cart import Cart
from eshop import payments as eshop_payments


from api.views._common import *  # noqa: F401,F403


class EshopCategoryListAPIView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]


class EshopProductListAPIView(generics.ListAPIView):
    serializer_class = ProductListSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["category__slug"]
    search_fields = ["name", "subtitle", "collection"]

    def get_queryset(self):
        return (
            Product.objects.filter(active=True)
            .select_related("category")
            .prefetch_related("variants")
        )


class EshopProductDetailAPIView(generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Product.objects.filter(active=True)
            .select_related("category")
            .prefetch_related("variants")
        )


class EshopCartAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            name="EshopCart",
            fields={
                "items": inline_serializer(
                    name="EshopCartItem",
                    many=True,
                    fields={
                        "variant_id": serializers.IntegerField(),
                        "product_id": serializers.IntegerField(),
                        "product_name": serializers.CharField(),
                        "product_slug": serializers.CharField(),
                        "variant_label": serializers.CharField(),
                        "price": serializers.DecimalField(max_digits=10, decimal_places=2),
                        "quantity": serializers.IntegerField(),
                        "stock": serializers.IntegerField(),
                        "subtotal": serializers.DecimalField(max_digits=10, decimal_places=2),
                    },
                ),
                "total": serializers.DecimalField(max_digits=10, decimal_places=2),
                "count": serializers.IntegerField(),
            },
        )
    )
    def get(self, request):
        cart = Cart(request)
        variant_ids = cart.variant_ids()
        if not variant_ids:
            return Response({"items": [], "total": "0", "count": 0})

        variant_map = {
            v.pk: v
            for v in ProductVariant.objects.select_related("product").filter(
                pk__in=variant_ids, active=True
            )
        }

        items = []
        total = 0
        for vid in variant_ids:
            qty = cart.get_quantity(vid)
            variant = variant_map.get(vid)
            if not variant or qty <= 0:
                continue
            subtotal = variant.price * qty
            total += subtotal
            items.append({
                "variant_id": vid,
                "product_id": variant.product_id,
                "product_name": variant.product.name,
                "product_slug": variant.product.slug,
                "variant_label": variant.label,
                "price": str(variant.price),
                "quantity": qty,
                "stock": variant.stock,
                "subtotal": str(subtotal),
            })

        return Response({"items": items, "total": str(total), "count": len(items)})

    @extend_schema(
        request=inline_serializer(
            name="EshopCartUpdateRequest",
            fields={
                "variant_id": serializers.IntegerField(),
                "quantity": serializers.IntegerField(default=1, min_value=0),
                "action": serializers.ChoiceField(choices=["add", "set"], default="add"),
            },
        ),
        responses={
            200: inline_serializer(
                name="EshopCartUpdateResponse",
                fields={
                    "ok": serializers.BooleanField(),
                    "quantity": serializers.IntegerField(),
                },
            ),
            400: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def post(self, request):
        try:
            variant_id = int(request.data.get("variant_id"))
            quantity = int(request.data.get("quantity", 1))
        except (TypeError, ValueError):
            return Response({"error": "Neplatná data."}, status=status.HTTP_400_BAD_REQUEST)

        if quantity < 0:
            return Response({"error": "Množství musí být kladné."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            variant = ProductVariant.objects.get(pk=variant_id, active=True)
        except ProductVariant.DoesNotExist:
            return Response({"error": "Varianta neexistuje."}, status=status.HTTP_404_NOT_FOUND)

        cart = Cart(request)
        action = request.data.get("action", "add")
        if action == "set":
            if quantity > variant.stock:
                return Response(
                    {"error": f"Na skladě je jen {variant.stock} ks."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cart.set(variant_id, quantity)
        else:
            new_qty = cart.get_quantity(variant_id) + quantity
            if new_qty > variant.stock:
                return Response(
                    {"error": f"Na skladě je jen {variant.stock} ks."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cart.add(variant_id, quantity)

        return Response({"ok": True, "quantity": cart.get_quantity(variant_id)})

    @extend_schema(
        operation_id="api_eshop_cart_clear",
        request=None,
        responses={204: OpenApiResponse(description="Košík vyprázdněn.")},
    )
    def delete(self, request):
        Cart(request).clear()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EshopCartItemAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="api_eshop_cart_item_destroy",
        request=None,
        responses={204: OpenApiResponse(description="Položka odstraněna z košíku.")},
    )
    def delete(self, request, variant_id):
        Cart(request).remove(variant_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EshopCheckoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name="EshopCheckoutRequest",
            fields={
                "first_name": serializers.CharField(),
                "last_name": serializers.CharField(),
                "email": serializers.EmailField(),
                "phone": serializers.CharField(required=False, allow_blank=True),
                "street": serializers.CharField(required=False, allow_blank=True),
                "city": serializers.CharField(required=False, allow_blank=True),
                "zip_code": serializers.CharField(required=False, allow_blank=True),
                "note": serializers.CharField(required=False, allow_blank=True),
                "event": serializers.IntegerField(),
            },
        ),
        responses={201: OrderSerializer, 400: ErrorSerializer},
    )
    def post(self, request):
        cart = Cart(request)
        if not cart:
            return Response({"error": "Košík je prázdný."}, status=status.HTTP_400_BAD_REQUEST)

        variant_ids = cart.variant_ids()
        variant_map = {
            v.pk: v
            for v in ProductVariant.objects.select_related("product").filter(
                pk__in=variant_ids, active=True
            )
        }

        items = []
        for vid in variant_ids:
            qty = cart.get_quantity(vid)
            variant = variant_map.get(vid)
            if not variant:
                return Response(
                    {"error": f"Varianta #{vid} už není dostupná."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if qty > variant.stock:
                return Response(
                    {"error": f"{variant.product.name} / {variant.label} — nedostatek kusů na skladě."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            items.append({"variant": variant, "quantity": qty})

        first_name = request.data.get("first_name", "").strip()
        last_name = request.data.get("last_name", "").strip()
        email = request.data.get("email", "").strip()
        event_id = request.data.get("event")

        if not first_name or not last_name or not email:
            return Response(
                {"error": "Vyplň jméno, příjmení a e-mail."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not event_id:
            return Response({"error": "Vyber závod pro předání."}, status=status.HTTP_400_BAD_REQUEST)

        cutoff = timezone.localdate() + timedelta(days=5)
        try:
            event = EventModel.objects.get(
                pk=event_id,
                date__gte=cutoff,
                eshop_pickup_enabled=True,
            )
        except EventModel.DoesNotExist:
            return Response(
                {"error": "Vybraný závod není dostupný pro předání."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with db_tx.atomic():
                order = Order.objects.create(
                    user=request.user,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    phone=request.data.get("phone", ""),
                    street=request.data.get("street", ""),
                    city=request.data.get("city", ""),
                    zip_code=request.data.get("zip_code", ""),
                    note=request.data.get("note", ""),
                    event=event,
                )
                OrderHistory.record(
                    order=order,
                    action=OrderHistory.Action.CREATED,
                    actor=request.user,
                    note="Objednávka vytvořena přes API.",
                )
                for item in items:
                    OrderItem.objects.create(
                        order=order,
                        variant=item["variant"],
                        quantity=item["quantity"],
                        unit_price=item["variant"].price,
                    )
                order.deduct_stock(actor=request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            stripe_session = eshop_payments.create_checkout_session(order)
        except eshop_payments.PaymentError as exc:
            order.cancel_by_user(actor=request.user, note="Platební bránu se nepodařilo otevřít.")
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        cart.clear()
        data = OrderSerializer(order, context={"request": request}).data
        data["checkout_url"] = stripe_session["url"]
        return Response(data, status=status.HTTP_201_CREATED)


class EshopOrderListAPIView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related("items__variant__product")
            .order_by("-created")
        )


class EshopOrderDetailAPIView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return Order.objects.filter(user=self.request.user).prefetch_related(
            "items__variant__product"
        )


class EshopOrderCancelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: OrderSerializer, 400: ErrorSerializer})
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, user=request.user)
        try:
            eshop_payments.cancel_order(order, actor=request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order, context={"request": request}).data)

__all__ = ['EshopCategoryListAPIView', 'EshopProductListAPIView', 'EshopProductDetailAPIView', 'EshopCartAPIView', 'EshopCartItemAPIView', 'EshopCheckoutAPIView', 'EshopOrderListAPIView', 'EshopOrderDetailAPIView', 'EshopOrderCancelAPIView']
