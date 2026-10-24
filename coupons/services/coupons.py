import secrets
import string

from django.conf import settings
from django.db import IntegrityError, transaction

from config.errors import ServiceError
from coupons.models import Coupon
from orders.models import OrderCounter
from orders.services.checkout import run_with_lock_retry


CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_coupon():
    try:
        return run_with_lock_retry(_generate_coupon_once)
    except IntegrityError as exc:
        raise ServiceError(
            "NO_ELIGIBLE_MILESTONE",
            "No unrewarded order milestone is currently eligible.",
            status_code=409,
        ) from exc


@transaction.atomic
def _generate_coupon_once():
    # BEGIN IMMEDIATE serializes this on SQLite. PostgreSQL uses this row as the
    # shared lock point with checkout, making the observed order count stable.
    counter, _ = OrderCounter.objects.get_or_create(pk=1, defaults={"last_order_number": 0})
    counter = OrderCounter.objects.select_for_update().get(pk=counter.pk)
    eligible_count = counter.last_order_number // settings.COUPON_EVERY_N_ORDERS
    generated = set(
        Coupon.objects.filter(milestone__lte=eligible_count).values_list("milestone", flat=True)
    )
    milestone = next(
        (number for number in range(1, eligible_count + 1) if number not in generated),
        None,
    )
    if milestone is None:
        raise ServiceError(
            "NO_ELIGIBLE_MILESTONE",
            "No unrewarded order milestone is currently eligible.",
            status_code=409,
        )

    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))
    return Coupon.objects.create(
        code=code,
        milestone=milestone,
        percent=settings.COUPON_DISCOUNT_PERCENT,
    )

