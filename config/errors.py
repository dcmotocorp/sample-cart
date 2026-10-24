from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class ServiceError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, code, message, *, details=None, status_code=None):
        self.code = code
        self.message = message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)


def error_response(code, message, *, details=None, status_code=400):
    return Response(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status=status_code,
    )


def exception_handler(exc, context):
    if isinstance(exc, ServiceError):
        return error_response(
            exc.code,
            exc.message,
            details=exc.details,
            status_code=exc.status_code,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        return response

    if response.status_code == 404:
        code, message = "NOT_FOUND", "The requested resource was not found."
    elif response.status_code == 405:
        code, message = "METHOD_NOT_ALLOWED", "This HTTP method is not allowed."
    elif response.status_code in (401, 403):
        code, message = "PERMISSION_DENIED", "Permission denied."
    else:
        code, message = "VALIDATION_ERROR", "Request validation failed."

    details = response.data if isinstance(response.data, (dict, list)) else {"detail": response.data}
    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response

