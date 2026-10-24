from rest_framework.generics import ListAPIView

from catalog.models import Product
from catalog.serializers import ProductSerializer


class ProductListView(ListAPIView):
    queryset = Product.objects.filter(is_active=True).order_by("id")
    serializer_class = ProductSerializer
    pagination_class = None

