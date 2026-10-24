from django.db import transaction
from django.db.models import Count, Max, Sum
from django.db.models.functions import Coalesce

from coupons.models import Coupon
from orders.models import Order, OrderItem


@transaction.atomic
def build_report():
    order_totals = Order.objects.aggregate(
        total_orders=Count("id"),
        gross=Coalesce(Sum("subtotal_minor"), 0),
        discounts=Coalesce(Sum("discount_minor"), 0),
        net=Coalesce(Sum("final_total_minor"), 0),
    )
    items = list(
        OrderItem.objects.values("product_id_snapshot")
        .annotate(name=Max("product_name"), quantity=Sum("quantity"))
        .order_by("product_id_snapshot")
    )
    coupon_counts = {
        row["status"]: row["count"]
        for row in Coupon.objects.values("status").annotate(count=Count("id"))
    }
    available = coupon_counts.get(Coupon.Status.AVAILABLE, 0)
    redeemed = coupon_counts.get(Coupon.Status.REDEEMED, 0)
    return {
        "items_sold_by_product": [
            {
                "product_id": row["product_id_snapshot"],
                "name": row["name"],
                "quantity": row["quantity"],
            }
            for row in items
        ],
        "gross_revenue_minor": order_totals["gross"],
        "total_discount_minor": order_totals["discounts"],
        "net_revenue_minor": order_totals["net"],
        "coupons": {
            "generated": available + redeemed,
            "available": available,
            "redeemed": redeemed,
        },
        "total_orders": order_totals["total_orders"],
    }

