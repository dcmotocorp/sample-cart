from rest_framework import serializers

from carts.models import Cart


MAX_QUANTITY = 9_223_372_036_854_775_807


class StrictQuantityField(serializers.IntegerField):
    def __init__(self, **kwargs):
        kwargs.setdefault("min_value", 1)
        kwargs.setdefault("max_value", MAX_QUANTITY)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail("invalid")
        return super().to_internal_value(data)


class AddCartItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    quantity = StrictQuantityField()


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = StrictQuantityField()


def serialize_cart(cart):
    lines = []
    warnings = []
    subtotal = 0
    for item in cart.items.select_related("product").order_by("product_id"):
        product = item.product
        line_total = product.unit_price_minor * item.quantity
        line_warnings = []
        if product.unit_price_minor != item.price_at_add_minor:
            warning = {
                "code": "PRICE_CHANGED",
                "product_id": product.id,
                "price_at_add_minor": item.price_at_add_minor,
                "current_price_minor": product.unit_price_minor,
            }
            line_warnings.append(warning)
            warnings.append(warning)
        if item.quantity > product.inventory:
            warning = {
                "code": "INSUFFICIENT_STOCK",
                "product_id": product.id,
                "requested": item.quantity,
                "available": product.inventory,
            }
            line_warnings.append(warning)
            warnings.append(warning)
        if not product.is_active:
            warning = {"code": "PRODUCT_INACTIVE", "product_id": product.id}
            line_warnings.append(warning)
            warnings.append(warning)
        lines.append(
            {
                "product_id": product.id,
                "name": product.name,
                "quantity": item.quantity,
                "unit_price_minor": product.unit_price_minor,
                "price_at_add_minor": item.price_at_add_minor,
                "line_total_minor": line_total,
                "warnings": line_warnings,
            }
        )
        subtotal += line_total
    return {
        "id": cart.id,
        "status": cart.status,
        "currency": "INR",
        "items": lines,
        "subtotal_minor": subtotal,
        "warnings": warnings,
        "created_at": cart.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": cart.updated_at.isoformat().replace("+00:00", "Z"),
    }

