from django.urls import path

from reports.views import ReportView


urlpatterns = [path("admin/report", ReportView.as_view(), name="admin-report")]

