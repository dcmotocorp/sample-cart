from django.db import migrations


def ensure_order_counter(apps, schema_editor):
    OrderCounter = apps.get_model("orders", "OrderCounter")
    OrderCounter.objects.get_or_create(pk=1, defaults={"last_order_number": 0})


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_order_order_coupon_snapshot_consistent_and_more")]
    operations = [migrations.RunPython(ensure_order_counter, migrations.RunPython.noop)]

