# Reliable Checkout and Rewards Service

A Django REST API for carts, inventory-safe checkout, retry-safe order creation, single-use coupons, and reconciliable reporting. Correctness under overlapping requests is the primary design goal.

Currency is INR. Every money value ending in `_minor` is an integer number of paise.

Approximate time spent: [fill in]

## Quick evaluation

Requires Python 3.12+.

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed
python manage.py runserver
```

Then open `http://127.0.0.1:8000/api/docs/` or follow [docs/API.md](docs/API.md).

The same workflow is available through:

```bash
make setup
make seed
make run
make test
```

Configuration defaults are shown in `.env.example`. Values are read from environment variables; no credentials or private services are required.

## Tests

```bash
python -m pytest -q
```

The suite uses a file-backed `test_db.sqlite3`; this is intentional because SQLite `:memory:` databases cannot be reliably shared by the real worker threads used in concurrency tests.

## Seed data

```bash
python manage.py seed
```

This creates five products and the singleton order counter. `Limited Saffron` has stock `2` for quick inventory-conflict experiments. Re-running the command updates the named seed products rather than duplicating them.

## API and administration

Public endpoints live under `/api/products`, `/api/carts`, and `/api/orders`. Administrative endpoints have no authentication for this assignment and are isolated under `/api/admin/`:

- `POST /api/admin/coupons/generate`
- `GET /api/admin/coupons`
- `GET /api/admin/report`

Interactive OpenAPI documentation is at `/api/docs/`; the schema is at `/api/schema/` and checked in as `docs/openapi.yaml`.

## Optional PostgreSQL run

The same code supports PostgreSQL through `DATABASE_URL`; no source changes are needed. Create a database, then run:

```bash
DATABASE_URL=postgres://checkout:password@localhost:5432/checkout python manage.py migrate
DATABASE_URL=postgres://checkout:password@localhost:5432/checkout python manage.py seed
DATABASE_URL=postgres://checkout:password@localhost:5432/checkout python -m pytest
DATABASE_URL=postgres://checkout:password@localhost:5432/checkout python manage.py runserver
```

In PowerShell, set `$env:DATABASE_URL` before the commands. PostgreSQL execution is optional and was not required for local evaluation.

## Project layout

- `catalog`: products and inventory
- `carts`: cart state, line validation, and current-price projections
- `orders`: checkout orchestration, snapshots, idempotency, and payment abstraction
- `coupons`: milestone generation and coupon state
- `reports`: read-only order/coupon projections
- `tests`: threaded concurrency, rollback, business-rule, and reconciliation tests

The detailed reasoning, invariants, concurrency analysis, trade-offs, and deferred work are in [DECISIONS.md](DECISIONS.md).
