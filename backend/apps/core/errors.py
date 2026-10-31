"""Business errors raised by services, and the API error format.

Services raise these plain exceptions (no DRF imports). The exception handler
turns them, and DRF's own errors, into one shape:

    {"error": {"code": "...", "message": "...", "fields": {...}}}
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class BusinessError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid"

    def __init__(self, message: str, code: str | None = None, fields: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.fields = fields or {}


class Invalid(BusinessError):
    pass


class Conflict(BusinessError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class Forbidden(BusinessError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


def _first_message(detail) -> str:
    if isinstance(detail, list) and detail:
        return _first_message(detail[0])
    if isinstance(detail, dict) and detail:
        key, value = next(iter(detail.items()))
        msg = _first_message(value)
        return msg if key in ("non_field_errors", "detail") else f"{key}: {msg}"
    return str(detail)


def exception_handler(exc, context):
    if isinstance(exc, BusinessError):
        body = {"code": exc.code, "message": exc.message}
        if exc.fields:
            body["fields"] = exc.fields
        return Response({"error": body}, status=exc.status_code)
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(
            exc.message_dict if hasattr(exc, "error_dict") else exc.messages
        )
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    detail = response.data
    code = getattr(exc, "default_code", "error")
    if isinstance(exc, exceptions.ValidationError):
        fields = detail if isinstance(detail, dict) else {"non_field_errors": detail}
        response.data = {
            "error": {"code": "validation", "message": _first_message(detail), "fields": fields}
        }
    else:
        message = detail.get("detail", detail) if isinstance(detail, dict) else detail
        response.data = {"error": {"code": code, "message": str(message)}}
    return response
