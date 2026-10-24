import hashlib
import json
import time
from dataclasses import dataclass

from django.db import OperationalError, close_old_connections, transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import Product
from carts.models import Cart
from config.errors import ServiceError
from orders.models import IdempotencyRecord, Order, OrderCounter, OrderItem
from orders.serializers import serialize_order
from orders.services.payments import PaymentGatewayError, get_payment_gateway


@dataclass(frozen=True)
class CheckoutResult:
    body: dict
    status_code: int
    replayed: bool = False


def request_hash(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_with_lock_retry(operation, *, attempts=8, base_delay=0.025):
    """Retry SQLite lock contention and PostgreSQL serialization/deadlock failures."""
    for attempt in range(attempts):
        try:
            return operation()
        except OperationalError:
            close_old_connections()
            if attempt == attempts - 1:
                raise
            time.sleep(base_delay * (2**attempt))


def checkout_cart(*, cart_id, idempotency_key, payload, gateway=None):
    gateway = gateway or get_payment_gateway()
    payload_digest = request_hash(payload)
    return run_with_lock_retry(
        lambda: _checkout_once(
            cart_id=cart_id,
            idempotency_key=idempotency_key,
            payload=payload,
            payload_digest=payload_digest,
            gateway=gateway,
        )
    )


@transaction.atomic
def _checkout_once(*, cart_id, idempotency_key, payload, payload_digest, gateway):
    # Lock order is deliberate and shared with coupon generation:
    # cart -> products by ascending id -> coupon (Phase 4) -> order counter.
    # select_for_update() is a no-op on SQLite; BEGIN IMMEDIATE serializes writers.
    try:
        cart = Cart.objects.select_for_update().get(pk=cart_id)
    except Cart.DoesNotExist as exc:
        raise ServiceError("CART_NOT_FOUND", "Cart not found.", status_code=404) from exc

    existing_record = IdempotencyRecord.objects.filter(
        cart=cart, scope="checkout", key=idempotency_key
    ).first()
    if existing_record:
        if existing_record.request_hash != payload_digest:
            raise ServiceError(
                "IDEMPOTENCY_KEY_REUSED",
                "This idempotency key was already used with a different request.",
                status_code=422,
            )
        return CheckoutResult(
            body=existing_record.response_body,
            status_code=existing_record.response_status,
            replayed=True,
        )

    if cart.status != Cart.Status.OPEN:
        order = Order.objects.filter(cart=cart).only("id").first()
        raise ServiceError(
            "CART_ALREADY_CHECKED_OUT",
            "This cart has already been checked out.",
            details={"order_id": order.id if order else None},
            status_code=409,
        )

    cart_items = list(cart.items.order_by("product_id"))
    if not cart_items:
        raise ServiceError("CART_EMPTY", "The cart is empty.", status_code=422)

    product_ids = [item.product_id for item in cart_items]
    products = {
        product.id: product
        for product in Product.objects.select_for_update()
        .filter(id__in=product_ids)
        .order_by("id")
    }

    invalid = [item.product_id for item in cart_items if not products.get(item.product_id) or not products[item.product_id].is_active]
    if invalid:
        raise ServiceError(
            "VALIDATION_ERROR",
            "The cart contains unavailable products.",
            details={"product_ids": invalid},
            status_code=400,
        )

    shortages = [
        {
            "product_id": item.product_id,
            "requested": item.quantity,
            "available": products[item.product_id].inventory,
        }
        for item in cart_items
        if item.quantity > products[item.product_id].inventory
    ]
    if shortages:
        raise ServiceError(
            "INSUFFICIENT_STOCK",
            "One or more products do not have enough stock.",
            details={"products": shortages},
            status_code=409,
        )

    if payload.get("coupon_code"):
        raise ServiceError(
            "COUPON_NOT_FOUND", "Coupon not found.", status_code=404
        )

    line_values = []
    price_changed = []
    subtotal = 0
    for item in cart_items:
        product = products[item.product_id]
        line_total = product.unit_price_minor * item.quantity
        line_values.append((item, product, line_total))
        subtotal += line_total
        if item.price_at_add_minor != product.unit_price_minor:
            price_changed.append(
                {
                    "product_id": product.id,
                    "price_at_add_minor": item.price_at_add_minor,
                    "charged_unit_price_minor": product.unit_price_minor,
                }
            )

    counter, _ = OrderCounter.objects.get_or_create(pk=1, defaults={"last_order_number": 0})
    counter = OrderCounter.objects.select_for_update().get(pk=counter.pk)
    counter.last_order_number = F("last_order_number") + 1
    counter.save(update_fields=["last_order_number"])
    counter.refresh_from_db(fields=["last_order_number"])

    order = Order.objects.create(
        cart=cart,
        order_number=counter.last_order_number,
        subtotal_minor=subtotal,
        discount_minor=0,
        final_total_minor=subtotal,
    )
    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product_id_snapshot=product.id,
                product_name=product.name,
                unit_price_minor=product.unit_price_minor,
                quantity=item.quantity,
                line_total_minor=line_total,
            )
            for item, product, line_total in line_values
        ]
    )
    for item, product, _ in line_values:
        product.inventory = F("inventory") - item.quantity
        product.save(update_fields=["inventory", "updated_at"])

    try:
        gateway.charge(
            amount_minor=order.final_total_minor,
            currency=order.currency,
            idempotency_key=idempotency_key,
        )
    except PaymentGatewayError as exc:
        raise ServiceError(
            "PAYMENT_FAILED",
            "Payment could not be completed.",
            details={},
            status_code=402,
        ) from exc

    cart.status = Cart.Status.CHECKED_OUT
    cart.checked_out_at = timezone.now()
    cart.save(update_fields=["status", "checked_out_at", "updated_at"])

    body = serialize_order(order, price_changed=price_changed)
    IdempotencyRecord.objects.create(
        cart=cart,
        scope="checkout",
        key=idempotency_key,
        request_hash=payload_digest,
        response_status=201,
        response_body=body,
    )
    return CheckoutResult(body=body, status_code=201)

