from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product
from carts.models import Cart, CartItem
from carts.serializers import (
    MAX_QUANTITY,
    AddCartItemSerializer,
    UpdateCartItemSerializer,
    serialize_cart,
)
from config.errors import ServiceError


def get_cart(cart_id, *, lock=False):
    queryset = Cart.objects.select_for_update() if lock else Cart.objects.all()
    try:
        return queryset.get(pk=cart_id)
    except Cart.DoesNotExist as exc:
        raise ServiceError("CART_NOT_FOUND", "Cart not found.", status_code=404) from exc


def require_open(cart):
    if cart.status != Cart.Status.OPEN:
        raise ServiceError(
            "CART_NOT_OPEN", "Only open carts may be modified.", status_code=409
        )


def validate(serializer):
    if not serializer.is_valid():
        raise ServiceError(
            "VALIDATION_ERROR",
            "Request validation failed.",
            details=serializer.errors,
            status_code=400,
        )
    return serializer.validated_data


class CartListCreateView(APIView):
    def post(self, request):
        cart = Cart.objects.create()
        return Response(serialize_cart(cart), status=status.HTTP_201_CREATED)


class CartDetailView(APIView):
    def get(self, request, cart_id):
        return Response(serialize_cart(get_cart(cart_id)))


class CartItemCreateView(APIView):
    @transaction.atomic
    def post(self, request, cart_id):
        data = validate(AddCartItemSerializer(data=request.data))
        cart = get_cart(cart_id, lock=True)
        require_open(cart)
        try:
            product = Product.objects.get(pk=data["product_id"])
        except Product.DoesNotExist as exc:
            raise ServiceError("PRODUCT_NOT_FOUND", "Product not found.", status_code=404) from exc
        if not product.is_active:
            raise ServiceError(
                "VALIDATION_ERROR",
                "Inactive products cannot be added.",
                details={"product_id": ["This product is inactive."]},
                status_code=400,
            )
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={
                "quantity": data["quantity"],
                "price_at_add_minor": product.unit_price_minor,
            },
        )
        if not created:
            new_quantity = item.quantity + data["quantity"]
            if new_quantity > MAX_QUANTITY:
                raise ServiceError(
                    "VALIDATION_ERROR",
                    "Request validation failed.",
                    details={"quantity": ["Resulting quantity is too large."]},
                )
            item.quantity = new_quantity
            item.save(update_fields=["quantity", "updated_at"])
        cart.refresh_from_db()
        return Response(
            serialize_cart(cart),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CartItemDetailView(APIView):
    @transaction.atomic
    def patch(self, request, cart_id, product_id):
        data = validate(UpdateCartItemSerializer(data=request.data))
        cart = get_cart(cart_id, lock=True)
        require_open(cart)
        try:
            item = CartItem.objects.get(cart=cart, product_id=product_id)
        except CartItem.DoesNotExist as exc:
            raise ServiceError(
                "PRODUCT_NOT_FOUND", "Product is not in this cart.", status_code=404
            ) from exc
        item.quantity = data["quantity"]
        item.save(update_fields=["quantity", "updated_at"])
        cart.refresh_from_db()
        return Response(serialize_cart(cart))

    @transaction.atomic
    def delete(self, request, cart_id, product_id):
        cart = get_cart(cart_id, lock=True)
        require_open(cart)
        deleted, _ = CartItem.objects.filter(cart=cart, product_id=product_id).delete()
        if not deleted:
            raise ServiceError(
                "PRODUCT_NOT_FOUND", "Product is not in this cart.", status_code=404
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

