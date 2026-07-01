from rest_framework import serializers
from .models import Category, Product, ProductVariant, Order, OrderItem


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "sort_order"]


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ["id", "label", "price", "stock", "active", "sort_order"]


class ProductListSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    image_url = serializers.SerializerMethodField()
    price_range = serializers.CharField(read_only=True)
    total_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "subtitle", "collection",
            "category", "category_name", "image_url",
            "variant_type", "active", "price_range", "total_stock", "variants",
        ]

    def get_image_url(self, obj) -> str | None:
        if not obj.image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class ProductDetailSerializer(ProductListSerializer):
    secondary_image_url = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "description", "material", "fit_note", "pickup_note",
            "secondary_image_url", "created", "updated",
        ]

    def get_secondary_image_url(self, obj) -> str | None:
        if not obj.secondary_image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.secondary_image.url) if request else obj.secondary_image.url


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    variant_label = serializers.CharField(source="variant.label", read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["id", "variant", "product_name", "variant_label", "quantity", "unit_price", "subtotal"]

    def get_subtotal(self, obj) -> str:
        return str(obj.unit_price * obj.quantity)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_paid = serializers.BooleanField(read_only=True)
    is_cancelable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "status", "status_display", "first_name", "last_name", "email",
            "phone", "street", "city", "zip_code", "note",
            "credits_charged", "invoice_number", "is_paid", "is_cancelable",
            "created", "updated", "items", "total",
        ]
        read_only_fields = [
            "id", "status", "credits_charged", "invoice_number",
            "is_paid", "is_cancelable", "created", "updated",
        ]

    def get_total(self, obj) -> str:
        return str(sum(item.unit_price * item.quantity for item in obj.items.all()))
