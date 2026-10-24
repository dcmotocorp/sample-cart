from django.urls import path

from orders.views import CheckoutView, OrderDetailView, OrderListView


urlpatterns = [
    path("carts/<int:cart_id>/checkout", CheckoutView.as_view(), name="checkout"),
    path("orders", OrderListView.as_view(), name="order-list"),
    path("orders/<int:order_id>", OrderDetailView.as_view(), name="order-detail"),
]

