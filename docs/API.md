# API Reference

Local base URL: `http://127.0.0.1:8000`. JSON money values are integer paise in INR. Every error is:

```json
{"error":{"code":"INSUFFICIENT_STOCK","message":"One or more products do not have enough stock.","details":{"products":[]}}}
```

## Public endpoints

### `GET /api/products`

Returns active products (`200`):

```json
[{"id":1,"name":"Masala Chai","unit_price_minor":19900,"currency":"INR","inventory":25,"is_active":true}]
```

### `POST /api/carts`

No body. Creates an open cart (`201`) and returns its projection.

### `GET /api/carts/{id}`

Returns (`200`) current unit prices, line totals, subtotal and warnings. `PRICE_CHANGED` compares current price with `price_at_add_minor`; `INSUFFICIENT_STOCK` reports requested and available. Error: `404 CART_NOT_FOUND`.

### `POST /api/carts/{id}/items`

Body: `{"product_id":1,"quantity":2}`. Creates a line (`201`). An existing product has its quantity increased and returns `200`; its original `price_at_add_minor` remains the warning baseline. Errors: `400 VALIDATION_ERROR` for non-integer/non-positive/too-large quantity or inactive product, `404 CART_NOT_FOUND`, `404 PRODUCT_NOT_FOUND`, `409 CART_NOT_OPEN`.

### `PATCH /api/carts/{id}/items/{product_id}`

Body: `{"quantity":3}`. Replaces quantity (`200`). Errors: `400 VALIDATION_ERROR`, `404 CART_NOT_FOUND`, `404 PRODUCT_NOT_FOUND`, `409 CART_NOT_OPEN`.

### `DELETE /api/carts/{id}/items/{product_id}`

Removes the line (`204`). Errors: `404 CART_NOT_FOUND`, `404 PRODUCT_NOT_FOUND`, `409 CART_NOT_OPEN`.

### `POST /api/carts/{id}/checkout`

Requires `Idempotency-Key`. Body is `{}` or `{"coupon_code":"AB12CD34EF"}`. Success (`201`) contains immutable order lines, totals, coupon snapshot and `price_changed`. Same key plus normalized payload returns the stored `201` body with `Idempotent-Replayed: true`.

Errors: `400 MISSING_IDEMPOTENCY_KEY`, `400 VALIDATION_ERROR`, `404 CART_NOT_FOUND`, `404 COUPON_NOT_FOUND`, `409 CART_ALREADY_CHECKED_OUT` (with existing `order_id`), `409 INSUFFICIENT_STOCK` (with shortages), `409 COUPON_ALREADY_REDEEMED`, `422 CART_EMPTY`, `422 IDEMPOTENCY_KEY_REUSED`, `402 PAYMENT_FAILED`.

Only successful responses are stored. Failed attempts roll back and may reuse the key after their cause is fixed.

### `GET /api/orders`

Returns all successful orders (`200`) in order-number order, allowing report reconciliation.

### `GET /api/orders/{id}`

Returns one order snapshot (`200`). Error: `404 ORDER_NOT_FOUND`.

## Administrative endpoints (no auth for this assignment)

### `POST /api/admin/coupons/generate`

No body. Generates the lowest unrewarded eligible milestone coupon (`201`). Error: `409 NO_ELIGIBLE_MILESTONE`.

### `GET /api/admin/coupons`

Returns coupons (`200`) with milestone, captured percent, status, timestamps and redeemed order id.

### `GET /api/admin/report`

Returns (`200`) purchased quantity by product, gross revenue, discount, net revenue, coupon counts and order count:

```json
{"items_sold_by_product":[{"product_id":1,"name":"Masala Chai","quantity":2}],"gross_revenue_minor":39800,"total_discount_minor":3980,"net_revenue_minor":35820,"coupons":{"generated":1,"available":0,"redeemed":1},"total_orders":1}
```

It is read-only and computed from orders, lines and coupons inside one transaction.

## Curl flows

### Happy path and retry

```bash
curl -s -X POST http://127.0.0.1:8000/api/carts
curl -s -X POST http://127.0.0.1:8000/api/carts/1/items -H "Content-Type: application/json" -d '{"product_id":1,"quantity":2}'
curl -i -X POST http://127.0.0.1:8000/api/carts/1/checkout -H "Content-Type: application/json" -H "Idempotency-Key: checkout-1" -d '{}'
# Retry after a lost response: identical body plus Idempotent-Replayed: true.
curl -i -X POST http://127.0.0.1:8000/api/carts/1/checkout -H "Content-Type: application/json" -H "Idempotency-Key: checkout-1" -d '{}'
```

### Conflict

```bash
curl -i -X POST http://127.0.0.1:8000/api/carts/1/checkout -H "Content-Type: application/json" -H "Idempotency-Key: checkout-1" -d '{"coupon_code":"DIFFERENT1"}'
# 422 IDEMPOTENCY_KEY_REUSED
```

### Coupon flow

```bash
# Run after the configured milestone is reached.
curl -s -X POST http://127.0.0.1:8000/api/admin/coupons/generate
curl -s http://127.0.0.1:8000/api/admin/coupons
curl -i -X POST http://127.0.0.1:8000/api/carts/2/checkout -H "Content-Type: application/json" -H "Idempotency-Key: coupon-order-2" -d '{"coupon_code":"AB12CD34EF"}'
curl -s http://127.0.0.1:8000/api/admin/report
```

