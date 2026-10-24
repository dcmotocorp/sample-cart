from django.db import models
from django.db.models import F, Q

from carts.models import Cart


class OrderCounter(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_order_number = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="single_order_counter_row")
        ]


class Order(models.Model):
    cart = models.OneToOneField(Cart, related_name="order", on_delete=models.PROTECT)
    order_number = models.PositiveBigIntegerField(unique=True)
    subtotal_minor = models.BigIntegerField()
    discount_minor = models.BigIntegerField(default=0)
    final_total_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="INR", editable=False)
    coupon_code = models.CharField(max_length=10, blank=True)
    coupon_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order_number"]
        constraints = [
            models.CheckConstraint(condition=Q(subtotal_minor__gte=0), name="order_subtotal_nonnegative"),
            models.CheckConstraint(condition=Q(discount_minor__gte=0), name="order_discount_nonnegative"),
            models.CheckConstraint(condition=Q(final_total_minor__gte=0), name="order_total_nonnegative"),
            models.CheckConstraint(condition=Q(discount_minor__lte=F("subtotal_minor")), name="order_discount_not_above_subtotal"),
            models.CheckConstraint(condition=Q(final_total_minor=F("subtotal_minor") - F("discount_minor")), name="order_total_matches_components"),
            models.CheckConstraint(condition=Q(coupon_percent__isnull=True) | Q(coupon_percent__range=(0, 100)), name="order_coupon_percent_valid"),
            models.CheckConstraint(
                condition=(
                    Q(coupon_code="", coupon_percent__isnull=True)
                    | (~Q(coupon_code="") & Q(coupon_percent__isnull=False))
                ),
                name="order_coupon_snapshot_consistent",
            ),
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.PROTECT)
    product_id_snapshot = models.PositiveBigIntegerField()
    product_name = models.CharField(max_length=200)
    unit_price_minor = models.BigIntegerField()
    quantity = models.PositiveBigIntegerField()
    line_total_minor = models.BigIntegerField()

    class Meta:
        ordering = ["product_id_snapshot"]
        constraints = [
            models.UniqueConstraint(fields=["order", "product_id_snapshot"], name="unique_product_snapshot_per_order"),
            models.CheckConstraint(condition=Q(unit_price_minor__gte=0), name="order_item_price_nonnegative"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="order_item_quantity_positive"),
            models.CheckConstraint(condition=Q(line_total_minor__gte=0), name="order_item_total_nonnegative"),
            models.CheckConstraint(condition=Q(line_total_minor=F("unit_price_minor") * F("quantity")), name="order_item_total_matches_components"),
        ]


class IdempotencyRecord(models.Model):
    cart = models.ForeignKey(Cart, related_name="idempotency_records", on_delete=models.PROTECT)
    scope = models.CharField(max_length=40, default="checkout")
    key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cart", "scope", "key"], name="unique_idempotency_key_per_cart_scope")
        ]

