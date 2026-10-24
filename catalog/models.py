from django.db import models
from django.db.models import Q


class Product(models.Model):
    name = models.CharField(max_length=200)
    unit_price_minor = models.BigIntegerField()
    inventory = models.BigIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(unit_price_minor__gte=0),
                name="product_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(inventory__gte=0),
                name="product_inventory_nonnegative",
            ),
        ]

    def __str__(self):
        return self.name

