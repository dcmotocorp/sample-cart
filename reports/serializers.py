from rest_framework import serializers


class ItemSoldSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    name = serializers.CharField()
    quantity = serializers.IntegerField()


class CouponCountsSerializer(serializers.Serializer):
    generated = serializers.IntegerField()
    available = serializers.IntegerField()
    redeemed = serializers.IntegerField()


class ReportSerializer(serializers.Serializer):
    items_sold_by_product = ItemSoldSerializer(many=True)
    gross_revenue_minor = serializers.IntegerField()
    total_discount_minor = serializers.IntegerField()
    net_revenue_minor = serializers.IntegerField()
    coupons = CouponCountsSerializer()
    total_orders = serializers.IntegerField()
