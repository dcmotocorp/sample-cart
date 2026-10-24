from django.contrib import admin

from orders.models import IdempotencyRecord, Order, OrderCounter, OrderItem


admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(OrderCounter)
admin.site.register(IdempotencyRecord)

