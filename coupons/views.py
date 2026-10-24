from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from coupons.models import Coupon
from coupons.serializers import CouponSerializer
from coupons.services.coupons import generate_coupon


class CouponGenerateView(APIView):
    def post(self, request):
        coupon = generate_coupon()
        return Response(CouponSerializer(coupon).data, status=status.HTTP_201_CREATED)


class CouponListView(ListAPIView):
    queryset = Coupon.objects.order_by("milestone")
    serializer_class = CouponSerializer
    pagination_class = None

