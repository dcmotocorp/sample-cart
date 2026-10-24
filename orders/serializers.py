from rest_framework import serializers

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


class OrderSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        return serialize_order(instance)

    class Meta:
        model = Order
        fields = ["id"]

