from rest_framework import serializers

from coupons.models import Coupon


class CouponSerializer(serializers.ModelSerializer):
    redeemed_by_order_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "status",
            "milestone",
            "percent",
            "created_at",
            "redeemed_at",
            "redeemed_by_order_id",
        ]

