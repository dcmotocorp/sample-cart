from rest_framework import serializers

from catalog.models import Product


class ProductSerializer(serializers.ModelSerializer):
    currency = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "unit_price_minor", "currency", "inventory", "is_active"]

    def get_currency(self, obj):
        return "INR"

