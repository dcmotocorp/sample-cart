from django.urls import path

from coupons.views import CouponGenerateView, CouponListView


urlpatterns = [
    path("admin/coupons/generate", CouponGenerateView.as_view(), name="coupon-generate"),
    path("admin/coupons", CouponListView.as_view(), name="coupon-list"),
]

