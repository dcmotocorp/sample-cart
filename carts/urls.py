from django.urls import path

from carts.views import CartDetailView, CartItemCreateView, CartItemDetailView, CartListCreateView


urlpatterns = [
    path("carts", CartListCreateView.as_view(), name="cart-create"),
    path("carts/<int:cart_id>", CartDetailView.as_view(), name="cart-detail"),
    path("carts/<int:cart_id>/items", CartItemCreateView.as_view(), name="cart-item-create"),
    path("carts/<int:cart_id>/items/<int:product_id>", CartItemDetailView.as_view(), name="cart-item-detail"),
]

