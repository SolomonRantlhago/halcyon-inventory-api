"""Standardised JSON error schema for every error the API returns.

Shape:
    {
      "error": {
        "status": 400,
        "code": "validation_error",
        "message": "Validation failed.",
        "details": {...} | [...] | null,
        "path": "/api/products/"
      }
    }
"""
import logging

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class ConflictError(exceptions.APIException):
    """Raised when a request is valid but clashes with current resource state."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state of the resource."
    default_code = "conflict"


def build_error(status_code, code, message, details=None, path=None):
    return {
        "error": {
            "status": status_code,
            "code": code,
            "message": message,
            "details": details,
            "path": path,
        }
    }


def _django_validation_details(exc):
    if hasattr(exc, "message_dict"):
        return exc.message_dict
    return exc.messages


def custom_exception_handler(exc, context):
    request = context.get("request")
    path = request.path if request is not None else None

    # Translate Django / database exceptions into DRF ones first.
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(_django_validation_details(exc))
    elif isinstance(exc, ProtectedError):
        exc = ConflictError("Cannot delete this resource because other records depend on it.")
    elif isinstance(exc, IntegrityError):
        exc = ConflictError("The request violates a database integrity constraint.")
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)

    if response is None:
        logger.exception("Unhandled exception", exc_info=exc)
        return Response(
            build_error(500, "server_error", "An unexpected error occurred.", path=path),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        code, message, details = "validation_error", "Validation failed.", response.data
    else:
        code = getattr(exc, "default_code", "error")
        message = str(getattr(exc, "detail", exc))
        details = None

    response.data = build_error(response.status_code, code, message, details, path)
    return response
