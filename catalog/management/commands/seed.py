from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Product
from orders.models import OrderCounter


PRODUCTS = [
    {"name": "Masala Chai", "unit_price_minor": 19900, "inventory": 25},
    {"name": "Filter Coffee", "unit_price_minor": 24900, "inventory": 20},
    {"name": "Mango Pickle", "unit_price_minor": 15900, "inventory": 12},
    {"name": "Limited Saffron", "unit_price_minor": 89900, "inventory": 2},
    {"name": "Jaggery Bites", "unit_price_minor": 9900, "inventory": 30},
]


class Command(BaseCommand):
    help = "Create or refresh deterministic local product seed data."

    @transaction.atomic
    def handle(self, *args, **options):
        for product_data in PRODUCTS:
            product, created = Product.objects.get_or_create(
                name=product_data["name"],
                defaults=product_data,
            )
            if not created:
                Product.objects.filter(pk=product.pk).update(
                    unit_price_minor=product_data["unit_price_minor"],
                    inventory=product_data["inventory"],
                    is_active=True,
                )

        OrderCounter.objects.get_or_create(pk=1, defaults={"last_order_number": 0})
        self.stdout.write(self.style.SUCCESS("Seeded 5 products and order counter."))

