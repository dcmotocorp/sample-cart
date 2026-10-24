from dataclasses import dataclass
from typing import Protocol


class PaymentGatewayError(Exception):
    """A payment authorization failed and checkout must roll back."""


@dataclass(frozen=True)
class PaymentReceipt:
    reference: str


class PaymentGateway(Protocol):
    def charge(self, *, amount_minor: int, currency: str, idempotency_key: str) -> PaymentReceipt:
        ...


class FakePaymentGateway:
    """Deterministic local gateway; tests can inject a failing implementation."""

    def charge(self, *, amount_minor, currency, idempotency_key):
        return PaymentReceipt(reference=f"fake-{idempotency_key}")


_default_gateway = FakePaymentGateway()


def get_payment_gateway():
    return _default_gateway

