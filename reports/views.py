from rest_framework.response import Response
from rest_framework.views import APIView

from reports.services.reports import build_report


class ReportView(APIView):
    def get(self, request):
        return Response(build_report())

