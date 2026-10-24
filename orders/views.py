from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.errors import ServiceError
from orders.models import Order
from orders.serializers import CheckoutRequestSerializer, OrderSerializer
from orders.services.checkout import checkout_cart


class CheckoutView(APIView):
    def post(self, request, cart_id):
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            raise ServiceError(
                "MISSING_IDEMPOTENCY_KEY",
                "The Idempotency-Key header is required.",
                status_code=400,
            )
        if len(idempotency_key) > 255:
            raise ServiceError(
                "VALIDATION_ERROR",
                "Request validation failed.",
                details={"Idempotency-Key": ["Must be at most 255 characters."]},
                status_code=400,
            )
        serializer = CheckoutRequestSerializer(data=request.data)
        if not serializer.is_valid():
            raise ServiceError(
                "VALIDATION_ERROR",
                "Request validation failed.",
                details=serializer.errors,
                status_code=400,
            )
        payload = serializer.validated_data
        result = checkout_cart(
            cart_id=cart_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        response = Response(result.body, status=result.status_code)
        if result.replayed:
            response["Idempotent-Replayed"] = "true"
        return response


class OrderListView(ListAPIView):
    queryset = Order.objects.prefetch_related("items").order_by("order_number")
    serializer_class = OrderSerializer
    pagination_class = None


class OrderDetailView(RetrieveAPIView):
    queryset = Order.objects.prefetch_related("items")
    serializer_class = OrderSerializer
    lookup_url_kwarg = "order_id"

    def get_object(self):
        try:
            return self.get_queryset().get(pk=self.kwargs[self.lookup_url_kwarg])
        except Order.DoesNotExist as exc:
            raise ServiceError("ORDER_NOT_FOUND", "Order not found.", status_code=404) from exc

