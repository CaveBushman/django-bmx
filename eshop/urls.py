from django.urls import path

from . import views

app_name = "eshop"

urlpatterns = [
    path("", views.index, name="index"),
    path("orders/<int:order_id>/admin/", views.admin_order_detail, name="admin-order-detail"),
    path("pickup-export.csv", views.export_pickup_orders_csv, name="pickup-export"),
    path("accounting-export.csv", views.export_accounting_orders_csv, name="accounting-export"),
    path("flexi-export.xml", views.export_flexi_xml, name="flexi-export"),
    path("pickup-print/", views.pickup_print_list, name="pickup-print"),
    path("pickup/<int:order_id>/shipped/", views.mark_pickup_order_shipped, name="pickup-shipped"),
    path("pickup/<int:order_id>/delivered/", views.mark_pickup_order_delivered, name="pickup-delivered"),
    path("shop/", views.shop, name="shop"),
    path("shop/<slug:slug>/", views.product_detail, name="product-detail"),
    path("shop/<slug:slug>/hlidat-dostupnost/", views.request_stock_alert, name="request-stock-alert"),
    path("cart/", views.cart, name="cart"),
    path("cart/add/", views.add_to_cart, name="add-to-cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("order/<int:order_id>/", views.order_confirmation, name="order-confirmation"),
    path("order/<int:order_id>/cancel/", views.cancel_order, name="cancel-order"),
    path("order/<int:order_id>/pay/", views.pay_with_credits, name="pay-with-credits"),
    path("order/<int:order_id>/faktura.pdf", views.download_invoice, name="download-invoice"),
    path("order/<int:order_id>/dobropis.pdf", views.download_credit_note, name="download-credit-note"),
    path("orders/", views.my_orders, name="my-orders"),
    path("tabulka-velikosti/", views.size_guide, name="size-guide"),
]
