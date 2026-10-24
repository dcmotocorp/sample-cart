# Engineering Decisions

## 1. System invariants

| Invariant | Where enforced |
|---|---|
| Stock never becomes negative | Locked checkout validation and transactional decrement; `product_inventory_nonnegative` DB check. |
| One order per cart | Locked cart status recheck, `OPEN -> CHECKED_OUT`, and unique `Order.cart` one-to-one. |
| Coupon redeemed at most once | Coupon lock, conditional `AVAILABLE -> REDEEMED` update, one-to-one redeemed order, and state-consistency DB check. |
| One coupon per milestone | Unique `Coupon.milestone`, locked counter generation, and clean `IntegrityError` handling. |
| One successful response per cart/scope/key | Unique idempotency constraint and lookup after the cart/write lock. |
| Order total equals line snapshots minus discount | Integer service calculation; line `price * quantity` checks; order `final = subtotal - discount` check. Cross-row subtotal equality is enforced by the sole order-creation service because SQL checks cannot aggregate children. |
| Discount is at most subtotal | `min` cap plus DB checks for non-negative total and `discount <= subtotal`. |
| Order history survives catalog changes | OrderItem snapshots product id/name/price/quantity/line total; Order snapshots all totals, currency and coupon. No update API exists. |
| Report is a function of orders/coupons | Read-only aggregation in `transaction.atomic`; reconciliation/non-mutation test. |
| Only committed orders advance milestones | Counter increment shares the order transaction; every failure rolls it back. |

## 2. Ambiguities and selected semantics

- Checkout charges the current locked product price. Cart view uses current price and `price_at_add_minor` only for warnings. Price changes do not block checkout.
- Adding an existing product increases quantity and retains the original price-warning baseline.
- Adding does not reserve stock. Checkout shortage fails the whole order, never partially fulfills.
- Inactive products cannot be added; an item deactivated later is warned about and rejected at checkout.
- One percentage coupon applies to the whole subtotal; coupons do not stack, expire, or belong to customers (there is no customer concept).
- An unused generated coupon remains available. An order using a coupon still counts toward milestones.
- “Successfully placed” means the checkout transaction committed after fake-payment success.
- Milestone `k` is eligible at `k * n` successful orders; generation selects the lowest missing eligible milestone.
- Coupon percentage is captured at generation, so later configuration does not alter issued coupons.
- Reports use immutable order snapshots and one transaction. Historical product quantity is grouped by product id with a deterministic snapshot name.
- Only successful checkout responses are persisted for idempotency. A failed request may retry its key after correction.

## Decision: SQLite locally and PostgreSQL-compatible locking

**Context:** Evaluation needs zero infrastructure without sacrificing overlap correctness.

**Options considered:** PostgreSQL-only; in-memory state; default SQLite; file SQLite with immediate transactions plus portable row-lock calls.

**Choice:** SQLite uses WAL, 20-second busy timeout, foreign keys, and `transaction_mode=IMMEDIATE`. `DATABASE_URL` selects PostgreSQL unchanged; ordered `select_for_update` calls remain.

**Why:** `BEGIN IMMEDIATE` takes SQLite's database write lock before read-then-write decisions. `select_for_update` is a no-op there. PostgreSQL uses the same calls as real row locks and allows unrelated writers to proceed.

**Consequences:** SQLite permits one writer at a time. Production should use PostgreSQL, pooling, deadlock/serialization retries, and lock metrics. The counter row may become hot; sequences, allocated ranges, or partitioning trade strict numbering for throughput.

## Decision: Pessimistic lock and revalidation

**Context:** Cart status, stock, coupon state, and counters are check-then-act races.

**Options considered:** Optimistic versions; serializable isolation; explicit pessimistic locks.

**Choice:** One atomic transaction locks cart, products ascending, optional coupon, then counter, and revalidates after locking.

**Why:** Expected conflicts are domain events and the critical section is auditable. Optimistic control needs versions/merge rules across four resources; serializable still needs retries.

**Consequences:** Contended requests wait. Fixed ordering avoids common deadlocks; bounded backoff handles lock/deadlock/serialization failures.

## Decision: Idempotency record plus unique cart order

**Context:** Clients retry lost responses concurrently and may accidentally change the payload.

**Options considered:** Only unique `Order.cart`; an external cache; transactional request-hash/response persistence.

**Choice:** Store `(cart, scope, key)`, canonical hash, status and body with a unique constraint, while retaining the one-order-per-cart constraint.

**Why:** Order uniqueness prevents duplication but cannot replay the exact response or detect changed input. Same-commit response storage makes effect and replay indivisible.

**Consequences:** Records need production retention. Only successes are stored. A different key on a checked-out cart returns `CART_ALREADY_CHECKED_OUT` and its order id.

## Decision: Integer minor-unit money

**Context:** Binary floating point cannot exactly represent many currency values.

**Options considered:** Float; decimal columns; integer paise.

**Choice:** `BigIntegerField` paise, single-currency INR.

**Why:** Arithmetic, JSON, equality constraints, and tests remain exact; fractional paise and conversion are out of scope.

**Consequences:** Clients format paise into rupees; multi-currency would require currency-specific scale rules.

## Decision: Coupon redemption inside order commit

**Context:** A coupon cannot be double-used or lost when checkout later fails.

**Options considered:** Redeem before checkout; redeem after commit; conditional transition inside checkout.

**Choice:** Lock the coupon and conditionally update `AVAILABLE -> REDEEMED` with the new order inside the checkout transaction.

**Why:** Inventory, order, coupon, cart, counter and replay state commit or roll back together. A zero-row update is an explicit conflict.

**Consequences:** Coupon and order ownership are coupled. Separate services would require reservation or saga semantics.

## Decision: Fake payment inside the transaction

**Context:** Payment failure must roll back all checkout effects and tests need injection.

**Options considered:** Call before transaction; commit then charge; injectable call immediately before commit.

**Choice:** `PaymentGateway`/`FakePaymentGateway` is injected and called inside the transaction. `PaymentGatewayError` becomes `402 PAYMENT_FAILED` and rolls back.

**Why:** This is deterministic and atomic for the assignment.

**Consequences:** A real network call must not hold locks this way. Production should use provider idempotency, authorize/capture, an outbox/webhooks, or a saga.

## Decision: Current price plus immutable order snapshots

**Context:** Product price can change between cart addition and checkout.

**Options considered:** Reserve add-time price; reject changes; charge current price and disclose it.

**Choice:** Charge current locked price, return `price_changed`, and snapshot charged fields.

**Why:** This meets the chosen policy without stale-price leakage and keeps the order explainable.

**Consequences:** Cart totals are estimates; a production UI should highlight material changes.

## Decision: Service-layer transaction ownership

**Context:** HTTP and tests need the same invariant-preserving operations.

**Options considered:** Logic in views/serializers; model hooks; explicit services.

**Choice:** Checkout, coupon generation, reporting and payments live in service modules; views translate HTTP.

**Why:** Transaction boundaries and lock order stay explicit and testable. Hooks obscure multi-row ordering.

**Consequences:** Services are the supported mutation path; future jobs and permission layers should call them.

## Decision: Fixed lock order

**Context:** Real PostgreSQL row locks can deadlock when workflows acquire shared rows differently.

**Options considered:** Incidental ORM ordering; retry-only; a documented global order.

**Choice:** Cart, products by ascending id, coupon, counter. Coupon generation locks its shared counter.

**Why:** Deterministic acquisition removes common wait cycles while retaining retry for database aborts.

**Consequences:** Every future workflow touching these resources must follow the order.

## 4. Transaction, concurrency, and idempotency strategy

Checkout executes in one `transaction.atomic` attempt:

1. SQLite begins `IMMEDIATE`; PostgreSQL begins normally.
2. Lock cart; look up `(cart, checkout, key)`.
3. If found, compare canonical payload hash: replay exact response or return `422 IDEMPOTENCY_KEY_REUSED`.
4. Revalidate open/non-empty cart.
5. Lock products ascending; revalidate active status and stock.
6. Lock and validate the supplied coupon.
7. Calculate current-price snapshots, subtotal, floored discount, and final total.
8. Lock/increment the singleton counter.
9. Insert the unique-cart order/lines and decrement inventory.
10. Conditionally redeem the coupon.
11. Call the gateway. Failure raises and rolls everything back.
12. Mark cart checked out; insert the successful response record; commit.
13. Retry boundedly on SQLite lock or PostgreSQL deadlock/serialization `OperationalError`.

No decision trusts data read before locking. SQLite row-lock calls do nothing; its `BEGIN IMMEDIATE` provides serialization. PostgreSQL uses the explicit locks.

## 5. Money and rounding

- INR only; all stored/API money is integer paise and never float.
- Line total is `unit_price_minor * quantity`.
- Discount is `subtotal_minor * percent // 100`: deterministic floor, in favor of the store.
- Discount is capped at subtotal, so total cannot be negative.
- Coupon percent and all charged values are snapshotted.

Thus 10% of `99,999` is `9,999`, while 10% of one paise is zero.

## 6. Error model

All errors use `{error: {code, message, details}}`; the custom DRF handler wraps framework parsing, validation, not-found, permission and method errors too.

`409` means valid input conflicts with current state (stock, closed cart, redeemed coupon, unavailable milestone). `422` means understood but unprocessable semantics (empty cart or key reused with another payload). Field/type errors are `400`, missing resources `404`, and the simulated payment failure `402`.

## 7. Implemented versus intentionally deferred

Implemented: products, carts, warnings, transactional checkout, immutable snapshots, file-SQLite concurrency, PostgreSQL lock path, idempotent replay, injectable fake payment, milestone coupons, atomic redemption, reports, OpenAPI, seed command, and risk-focused tests.

Deferred: authentication/authorization, customers, coupon expiry/customer scope/stacking, inventory reservation on add, pagination, rate limiting, real payments/webhooks, audit log, idempotency cleanup, taxes/shipping, multiple currencies, product administration, and async reports.

## 8. Multiple instances and production scale

Use PostgreSQL: row locks and unique constraints coordinate every instance, and the DB idempotency table remains authoritative. Add pooling and metrics for checkout duration, lock wait/retries, inventory/coupon conflicts, gateway latency, and reconciliation.

Use provider idempotency plus authorize/capture and an outbox for payment commands/webhooks. High-demand stock may need TTL reservations. Reports can use a replica/projection with documented freshness. Replace the hot counter with a sequence, allocated ranges, or shards if strict numbering can relax. Redis may cache reads but is never the source of truth for stock, coupons, or idempotency. Keep bounded, jittered deadlock/serialization retries.

## 9. How AI tools were used

> [I MUST REPLACE THIS WITH MY OWN HONEST ACCOUNT]

Replace that block before submission using:

- **What I used AI for:** [design, scaffolding, tests, documentation, review]
- **What I verified by running:** [exact commands and observed results]
- **One correction/rejection/redirection:** [what was wrong and what changed]

Candidate examples—keep only one that genuinely happened and delete the others:

1. A first draft checked stock before taking the lock; redirect it so reads/decrements occur after cart/product locks.
2. A draft redeemed a coupon outside the order transaction; move it inside so payment rollback restores availability.
3. A draft used float discount math; replace it with `subtotal * percent // 100` and a cap.

Do not claim a candidate without evidence. A visible real example is the initial report non-mutation test capturing stale in-memory stock; the failing assertion was corrected to reread the DB and the full suite was rerun.

## 10. What I would examine first with another two hours

Repeated stress runs and a PostgreSQL CI job would come first, exercising real row locks and inspecting lock waits/query plans. Next: schema tests for every error, property-based money/quantity boundaries, deliberate deadlock/serialization fault injection, idempotency retention, and a clearer historical-name policy for reports.

## What would these tests catch?

- **Oversell:** without the write/product lock, ten threads can all pass a stale stock check.
- **Same coupon:** without lock plus conditional update, several carts can read `AVAILABLE` and discount.
- **Same cart/same key:** without transactional response persistence, retries can duplicate effects or return drifted bodies.
- **Same cart/different keys:** without unique cart/order and state recheck, keys bypass idempotency.
- **Concurrent generation:** without counter lock and unique milestone, generators issue duplicate rewards.
- **Payment rollback:** detects inventory/coupon/cart/replay writes outside the transaction.
- **Multi-line shortage:** detects decrement-as-you-iterate partial orders.
- **Invalid coupon:** detects validating after inventory mutation.
- **Sequential retry:** detects response drift and keys not bound to payload.
- **Price snapshot:** detects stale charging or mutable history.
- **Money boundaries:** detects floats, rounding up, and negative totals.
- **Milestones:** detects off-by-one, duplicate and out-of-order rewards.
- **Cart validation:** detects string coercion, invalid bounds, unknown products, and closed-cart mutation.
- **Report reconciliation:** detects current-catalog/cart dependence, revenue mistakes, count drift, or mutating GET.

Each concurrency test would fail against the corresponding naive implementation without its lock/transaction: threads synchronize before the competing call and assertions inspect final durable state, not merely response codes.

