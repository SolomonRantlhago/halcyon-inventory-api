import time

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import build_error

STARTED_AT = time.monotonic()
STARTED_AT_ISO = timezone.now().isoformat()


class HealthView(APIView):
    """Liveness/readiness probe: database connectivity, uptime and service status."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["health"],
        auth=[],
        responses={
            200: inline_serializer(
                "HealthOK",
                {
                    "status": serializers.CharField(),
                    "service": serializers.CharField(),
                    "version": serializers.CharField(),
                    "uptime_seconds": serializers.FloatField(),
                    "started_at": serializers.CharField(),
                    "timestamp": serializers.CharField(),
                    "database": serializers.DictField(),
                },
            ),
            503: None,
        },
    )
    def get(self, request):
        db = {"status": "up", "vendor": connection.vendor}
        try:
            start = time.perf_counter()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            db["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        except Exception as exc:  # noqa: BLE001 - any DB failure means "down"
            db = {"status": "down", "vendor": connection.vendor, "error": exc.__class__.__name__}

        healthy = db["status"] == "up"
        payload = {
            "status": "ok" if healthy else "degraded",
            "service": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
            "uptime_seconds": round(time.monotonic() - STARTED_AT, 2),
            "started_at": STARTED_AT_ISO,
            "timestamp": timezone.now().isoformat(),
            "database": db,
        }
        return Response(
            payload,
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def not_found(request, exception=None):
    return JsonResponse(
        build_error(404, "not_found", "The requested resource was not found.", path=request.path),
        status=404,
    )


def server_error(request):
    return JsonResponse(
        build_error(500, "server_error", "An unexpected error occurred.", path=request.path),
        status=500,
    )
