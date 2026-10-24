from django.db import models
from django.db.models import Q

from orders.models import Order


class Coupon(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        REDEEMED = "REDEEMED", "Redeemed"

    code = models.CharField(max_length=10, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE)
    milestone = models.PositiveBigIntegerField(unique=True)
    percent = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_by_order = models.OneToOneField(
        Order, related_name="redeemed_coupon", null=True, blank=True, on_delete=models.PROTECT
    )

    class Meta:
        ordering = ["milestone"]
        constraints = [
            models.CheckConstraint(condition=Q(percent__range=(0, 100)), name="coupon_percent_valid"),
            models.CheckConstraint(condition=Q(milestone__gt=0), name="coupon_milestone_positive"),
            models.CheckConstraint(
                condition=(
                    Q(status="AVAILABLE", redeemed_at__isnull=True, redeemed_by_order__isnull=True)
                    | Q(status="REDEEMED", redeemed_at__isnull=False, redeemed_by_order__isnull=False)
                ),
                name="coupon_redemption_state_consistent",
            ),
        ]

