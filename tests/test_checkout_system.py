from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from catalog.models import Product
from carts.models import Cart, CartItem
from config.errors import ServiceError
from coupons.models import Coupon
from coupons.services.coupons import generate_coupon
from orders.models import IdempotencyRecord, Order, OrderCounter
from orders.services.checkout import checkout_cart
from orders.services.payments import PaymentGatewayError


class FailingGateway:
    def charge(self, **kwargs):
        raise PaymentGatewayError("simulated decline")


class CheckoutSystemTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.product = Product.objects.create(
            name="Test Product", unit_price_minor=99_999, inventory=100
        )
        OrderCounter.objects.create(pk=1, last_order_number=0)

    def make_cart(self, product=None, quantity=1):
        product = product or self.product
        cart = Cart.objects.create()
        CartItem.objects.create(
            cart=cart,
            product=product,
            quantity=quantity,
            price_at_add_minor=product.unit_price_minor,
        )
        return cart

    def place_order(self, *, product=None, quantity=1, key=None, coupon_code=None, gateway=None):
        cart = self.make_cart(product, quantity)
        payload = {"coupon_code": coupon_code} if coupon_code else {}
        return checkout_cart(
            cart_id=cart.id,
            idempotency_key=key or f"order-{cart.id}",
            payload=payload,
            gateway=gateway,
        )

    def run_concurrently(self, count, function):
        barrier = Barrier(count)

        def invoke(index):
            close_old_connections()
            barrier.wait()
            try:
                return function(index)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=count) as executor:
            return list(executor.map(invoke, range(count)))

    # Catches a check-then-decrement stock race that lets overlapping carts oversell.
    def test_concurrent_checkouts_never_oversell(self):
        limited = Product.objects.create(name="Limited", unit_price_minor=500, inventory=2)
        carts = [self.make_cart(limited) for _ in range(10)]

        def attempt(index):
            try:
                checkout_cart(cart_id=carts[index].id, idempotency_key=f"stock-{index}", payload={})
                return "success"
            except ServiceError as exc:
                return exc.code

        results = self.run_concurrently(10, attempt)
        limited.refresh_from_db()
        self.assertEqual(results.count("success"), 2)
        self.assertEqual(results.count("INSUFFICIENT_STOCK"), 8)
        self.assertEqual(limited.inventory, 0)
        self.assertEqual(Order.objects.count(), 2)

    # Catches read-modify-write coupon redemption that discounts multiple orders.
    def test_concurrent_carts_redeem_coupon_once(self):
        coupon = Coupon.objects.create(code="ONECOUPON1", milestone=1, percent=10)
        carts = [self.make_cart() for _ in range(3)]

        def attempt(index):
            try:
                checkout_cart(
                    cart_id=carts[index].id,
                    idempotency_key=f"coupon-{index}",
                    payload={"coupon_code": coupon.code},
                )
                return "success"
            except ServiceError as exc:
                return exc.code

        results = self.run_concurrently(3, attempt)
        coupon.refresh_from_db()
        self.assertEqual(results.count("success"), 1)
        self.assertEqual(results.count("COUPON_ALREADY_REDEEMED"), 2)
        self.assertEqual(coupon.status, Coupon.Status.REDEEMED)
        self.assertEqual(Order.objects.filter(discount_minor__gt=0).count(), 1)

    # Catches retry handling that creates multiple orders or decrements stock repeatedly.
    def test_concurrent_same_key_replays_one_checkout(self):
        cart = self.make_cart()
        starting_stock = self.product.inventory

        def attempt(index):
            return checkout_cart(cart_id=cart.id, idempotency_key="same-key", payload={})

        results = self.run_concurrently(10, attempt)
        self.product.refresh_from_db()
        self.assertEqual(Order.objects.filter(cart=cart).count(), 1)
        self.assertEqual(self.product.inventory, starting_stock - 1)
        self.assertTrue(all(result.status_code == 201 for result in results))
        self.assertTrue(all(result.body == results[0].body for result in results))
        self.assertEqual(sum(not result.replayed for result in results), 1)

    # Catches relying on idempotency keys alone instead of the one-order-per-cart invariant.
    def test_concurrent_different_keys_create_one_order(self):
        cart = self.make_cart()

        def attempt(index):
            try:
                checkout_cart(cart_id=cart.id, idempotency_key=f"different-{index}", payload={})
                return "success"
            except ServiceError as exc:
                return exc.code

        results = self.run_concurrently(6, attempt)
        self.assertEqual(results.count("success"), 1)
        self.assertEqual(results.count("CART_ALREADY_CHECKED_OUT"), 5)
        self.assertEqual(Order.objects.filter(cart=cart).count(), 1)

    # Catches duplicate rewards caused by concurrent milestone checks without a shared lock.
    @override_settings(COUPON_EVERY_N_ORDERS=5)
    def test_concurrent_coupon_generation_creates_one_milestone(self):
        for index in range(5):
            self.place_order(key=f"reward-order-{index}")

        def attempt(index):
            try:
                generate_coupon()
                return "success"
            except ServiceError as exc:
                return exc.code

        results = self.run_concurrently(10, attempt)
        self.assertEqual(results.count("success"), 1)
        self.assertEqual(results.count("NO_ELIGIBLE_MILESTONE"), 9)
        self.assertEqual(Coupon.objects.filter(milestone=1).count(), 1)

    # Catches payment failures committing inventory, coupon, cart, order, or idempotency state.
    def test_payment_failure_rolls_back_and_retry_succeeds(self):
        coupon = Coupon.objects.create(code="PAYFAIL001", milestone=1, percent=10)
        cart = self.make_cart()
        starting_stock = self.product.inventory
        with self.assertRaises(ServiceError) as caught:
            checkout_cart(
                cart_id=cart.id,
                idempotency_key="payment-retry",
                payload={"coupon_code": coupon.code},
                gateway=FailingGateway(),
            )
        self.assertEqual(caught.exception.code, "PAYMENT_FAILED")
        self.product.refresh_from_db()
        coupon.refresh_from_db()
        cart.refresh_from_db()
        self.assertEqual(self.product.inventory, starting_stock)
        self.assertEqual(coupon.status, Coupon.Status.AVAILABLE)
        self.assertEqual(cart.status, Cart.Status.OPEN)
        self.assertFalse(Order.objects.filter(cart=cart).exists())
        self.assertFalse(IdempotencyRecord.objects.filter(cart=cart).exists())
        result = checkout_cart(
            cart_id=cart.id,
            idempotency_key="payment-retry",
            payload={"coupon_code": coupon.code},
        )
        self.assertEqual(result.status_code, 201)

    # Catches partial inventory mutation when a later line fails stock validation.
    def test_multi_item_stock_failure_is_all_or_nothing(self):
        available = Product.objects.create(name="Available", unit_price_minor=100, inventory=5)
        short = Product.objects.create(name="Short", unit_price_minor=200, inventory=1)
        cart = self.make_cart(available, 2)
        CartItem.objects.create(cart=cart, product=short, quantity=2, price_at_add_minor=200)
        with self.assertRaises(ServiceError) as caught:
            checkout_cart(cart_id=cart.id, idempotency_key="multi-short", payload={})
        self.assertEqual(caught.exception.code, "INSUFFICIENT_STOCK")
        available.refresh_from_db()
        short.refresh_from_db()
        self.assertEqual((available.inventory, short.inventory), (5, 1))
        self.assertFalse(Order.objects.filter(cart=cart).exists())

    # Catches invalid-coupon handling that mutates stock or consumes the cart before failing.
    def test_invalid_coupon_consumes_nothing(self):
        cart = self.make_cart()
        starting_stock = self.product.inventory
        with self.assertRaises(ServiceError) as caught:
            checkout_cart(
                cart_id=cart.id,
                idempotency_key="invalid-coupon",
                payload={"coupon_code": "NOTREAL001"},
            )
        self.assertEqual(caught.exception.code, "COUPON_NOT_FOUND")
        self.product.refresh_from_db()
        cart.refresh_from_db()
        self.assertEqual(self.product.inventory, starting_stock)
        self.assertEqual(cart.status, Cart.Status.OPEN)
        self.assertFalse(Order.objects.filter(cart=cart).exists())

    # Catches non-idempotent sequential retries and payload/key ambiguity.
    def test_sequential_idempotency_replay_and_key_reuse_conflict(self):
        cart = self.make_cart()
        url = f"/api/carts/{cart.id}/checkout"
        first = self.client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="retry-key")
        replay = self.client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="retry-key")
        conflict = self.client.post(
            url,
            {"coupon_code": "DIFFERENT1"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="retry-key",
        )
        self.assertEqual((first.status_code, replay.status_code), (201, 201))
        self.assertEqual(first.json(), replay.json())
        self.assertEqual(replay["Idempotent-Replayed"], "true")
        self.assertEqual(conflict.status_code, 422)
        self.assertEqual(conflict.json()["error"]["code"], "IDEMPOTENCY_KEY_REUSED")

    # Catches charging a stale cart price or retaining a live product reference in order history.
    def test_checkout_uses_current_price_and_order_snapshot_is_immutable(self):
        cart = self.make_cart()
        self.product.unit_price_minor = 120_001
        self.product.save(update_fields=["unit_price_minor", "updated_at"])
        result = checkout_cart(cart_id=cart.id, idempotency_key="new-price", payload={})
        order = Order.objects.get(cart=cart)
        item = order.items.get()
        self.assertEqual(item.unit_price_minor, 120_001)
        self.assertEqual(result.body["price_changed"][0]["price_at_add_minor"], 99_999)
        self.product.unit_price_minor = 1
        self.product.name = "Renamed"
        self.product.save()
        item.refresh_from_db()
        self.assertEqual((item.unit_price_minor, item.product_name), (120_001, "Test Product"))

    # Catches floating-point or rounding-up discount calculations and negative totals.
    def test_money_rounding_is_integer_floor_and_total_never_negative(self):
        cases = [(99_999, 10, 9_999), (1, 10, 0), (1, 100, 1)]
        for index, (price, percent, expected_discount) in enumerate(cases, start=1):
            product = Product.objects.create(name=f"Money {index}", unit_price_minor=price, inventory=1)
            coupon = Coupon.objects.create(code=f"MONEY{index:05d}", milestone=index, percent=percent)
            result = self.place_order(
                product=product,
                coupon_code=coupon.code,
                key=f"money-{index}",
            )
            self.assertEqual(result.body["discount_minor"], expected_discount)
            self.assertGreaterEqual(result.body["final_total_minor"], 0)
            self.assertIs(type(result.body["subtotal_minor"]), int)
            self.assertIs(type(result.body["discount_minor"]), int)
            self.assertIs(type(result.body["final_total_minor"]), int)

    # Catches off-by-one eligibility, duplicate milestones, and out-of-order reward generation.
    @override_settings(COUPON_EVERY_N_ORDERS=2, COUPON_DISCOUNT_PERCENT=15)
    def test_coupon_generation_milestones_are_exact_and_ordered(self):
        with self.assertRaises(ServiceError) as before:
            generate_coupon()
        self.assertEqual(before.exception.code, "NO_ELIGIBLE_MILESTONE")
        self.place_order(key="milestone-a")
        with self.assertRaises(ServiceError):
            generate_coupon()
        self.place_order(key="milestone-b")
        first = generate_coupon()
        self.assertEqual((first.milestone, first.percent), (1, 15))
        with self.assertRaises(ServiceError):
            generate_coupon()
        self.place_order(key="milestone-c")
        self.place_order(key="milestone-d")
        second = generate_coupon()
        self.assertEqual(second.milestone, 2)
        self.assertEqual(list(Coupon.objects.values_list("milestone", flat=True)), [1, 2])

    # Catches permissive quantity coercion, missing product checks, and post-checkout cart edits.
    def test_cart_validation_rejects_invalid_quantities_products_and_closed_cart(self):
        cart_id = self.client.post("/api/carts", {}, format="json").json()["id"]
        url = f"/api/carts/{cart_id}/items"
        for quantity in (0, -1, "2", 9_223_372_036_854_775_808):
            response = self.client.post(
                url, {"product_id": self.product.id, "quantity": quantity}, format="json"
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        unknown = self.client.post(url, {"product_id": 999_999, "quantity": 1}, format="json")
        self.assertEqual((unknown.status_code, unknown.json()["error"]["code"]), (404, "PRODUCT_NOT_FOUND"))
        self.client.post(url, {"product_id": self.product.id, "quantity": 1}, format="json")
        self.client.post(
            f"/api/carts/{cart_id}/checkout",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="close-cart",
        )
        closed = self.client.patch(
            f"/api/carts/{cart_id}/items/{self.product.id}", {"quantity": 2}, format="json"
        )
        self.assertEqual((closed.status_code, closed.json()["error"]["code"]), (409, "CART_NOT_OPEN"))

    # Catches report drift, wrong revenue basis, coupon-count errors, and mutating GET behavior.
    def test_report_reconciles_with_orders_and_coupons_without_mutation(self):
        self.place_order(key="report-plain")
        coupon = Coupon.objects.create(code="REPORT0001", milestone=1, percent=10)
        self.place_order(key="report-discount", coupon_code=coupon.code)
        before = {
            "orders": Order.objects.count(),
            "coupons": list(Coupon.objects.values()),
            "stock": Product.objects.get(pk=self.product.pk).inventory,
        }
        first = self.client.get("/api/admin/report")
        second = self.client.get("/api/admin/report")
        orders = self.client.get("/api/orders").json()
        coupons = self.client.get("/api/admin/coupons").json()
        report = first.json()
        self.assertEqual(first.json(), second.json())
        self.assertEqual(report["total_orders"], len(orders))
        self.assertEqual(report["gross_revenue_minor"], sum(o["subtotal_minor"] for o in orders))
        self.assertEqual(report["total_discount_minor"], sum(o["discount_minor"] for o in orders))
        self.assertEqual(report["net_revenue_minor"], sum(o["final_total_minor"] for o in orders))
        self.assertEqual(
            report["net_revenue_minor"],
            report["gross_revenue_minor"] - report["total_discount_minor"],
        )
        self.assertEqual(report["coupons"]["generated"], len(coupons))
        after = {
            "orders": Order.objects.count(),
            "coupons": list(Coupon.objects.values()),
            "stock": Product.objects.get(pk=self.product.pk).inventory,
        }
        self.assertEqual(before, after)

