from django.db import models
from django.db.models import Q

from catalog.models import Product


class Cart(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CHECKED_OUT = "CHECKED_OUT", "Checked out"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status="OPEN", checked_out_at__isnull=True)
                    | Q(status="CHECKED_OUT", checked_out_at__isnull=False)
                ),
                name="cart_status_timestamp_consistent",
            )
        ]


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="cart_items", on_delete=models.PROTECT)
    quantity = models.PositiveBigIntegerField()
    price_at_add_minor = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"], name="unique_product_per_cart"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="cart_item_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(price_at_add_minor__gte=0),
                name="cart_item_price_at_add_nonnegative",
            ),
        ]

