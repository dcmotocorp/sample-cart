from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from reports.serializers import ReportSerializer
from reports.services.reports import build_report


class ReportView(APIView):
    @extend_schema(responses=ReportSerializer)
    def get(self, request):
        return Response(build_report())

