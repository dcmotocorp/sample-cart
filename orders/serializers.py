from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from orders.models import Order


class CheckoutRequestSerializer(serializers.Serializer):
    coupon_code = serializers.CharField(required=False, allow_blank=False, max_length=10)

    def validate_coupon_code(self, value):
        return value.strip().upper()


def serialize_order(order, *, price_changed=None):
    data = {
        "id": order.id,
        "order_number": order.order_number,
        "cart_id": order.cart_id,
        "currency": order.currency,
        "items": [
            {
                "product_id": item.product_id_snapshot,
                "name": item.product_name,
                "unit_price_minor": item.unit_price_minor,
                "quantity": item.quantity,
                "line_total_minor": item.line_total_minor,
            }
            for item in order.items.order_by("product_id_snapshot")
        ],
        "subtotal_minor": order.subtotal_minor,
        "discount_minor": order.discount_minor,
        "final_total_minor": order.final_total_minor,
        "coupon_used": (
            {"code": order.coupon_code, "percent": order.coupon_percent}
            if order.coupon_code
            else None
        ),
        "created_at": order.created_at.isoformat().replace("+00:00", "Z"),
    }
    if price_changed is not None:
        data["price_changed"] = price_changed
    return data


class OrderItemSnapshotSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(source="product_id_snapshot")
    name = serializers.CharField(source="product_name")
    unit_price_minor = serializers.IntegerField()
    quantity = serializers.IntegerField()
    line_total_minor = serializers.IntegerField()


class CouponSnapshotSerializer(serializers.Serializer):
    code = serializers.CharField()
    percent = serializers.IntegerField()


class PriceChangedSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    price_at_add_minor = serializers.IntegerField()
    charged_unit_price_minor = serializers.IntegerField()


class OrderSerializer(serializers.ModelSerializer):
    cart_id = serializers.IntegerField(read_only=True)
    items = OrderItemSnapshotSerializer(many=True, read_only=True)
    coupon_used = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "cart_id",
            "currency",
            "items",
            "subtotal_minor",
            "discount_minor",
            "final_total_minor",
            "coupon_used",
            "created_at",
        ]

    @extend_schema_field(CouponSnapshotSerializer(allow_null=True))
    def get_coupon_used(self, obj):
        if not obj.coupon_code:
            return None
        return {"code": obj.coupon_code, "percent": obj.coupon_percent}


class CheckoutResponseSerializer(OrderSerializer):
    price_changed = PriceChangedSerializer(many=True)

    class Meta(OrderSerializer.Meta):
        fields = [*OrderSerializer.Meta.fields, "price_changed"]

