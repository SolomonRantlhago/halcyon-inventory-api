from unittest import mock
from rest_framework.test import APITestCase
from django.db import IntegrityError
from accounts.models import User


class HealthTests(APITestCase):
    def test_health_ok_without_auth(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"]["status"], "up")
        self.assertIn("uptime_seconds", body)
        self.assertIn("service", body)

    def test_health_reports_database_down(self):
        with mock.patch("core.views.connection") as conn:
            conn.vendor = "postgresql"
            conn.cursor.side_effect = Exception("boom")
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "degraded")
        self.assertEqual(response.json()["database"]["status"], "down")


class ErrorHandlingTests(APITestCase):
    def test_unknown_route_returns_json_404(self):
        response = self.client.get("/nope/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_unhandled_exception_returns_json_500(self):
        admin = User.objects.create_superuser("root", "r@example.com", "Str0ngPass!23")
        self.client.force_authenticate(admin)
        with mock.patch(
            "inventory.views.SupplierViewSet.get_queryset", side_effect=RuntimeError("x")
        ), self.assertLogs("core.exceptions", level="ERROR"):
            self.client.raise_request_exception = False
            response = self.client.get("/api/suppliers/")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "server_error")

    def test_integrity_error_maps_to_409(self):
        admin = User.objects.create_superuser("root", "r@example.com", "Str0ngPass!23")
        self.client.force_authenticate(admin)
        with mock.patch(
            "inventory.views.SupplierViewSet.get_queryset", side_effect=IntegrityError("dup")
        ):
            response = self.client.get("/api/suppliers/")
        self.assertEqual(response.status_code, 409)

    def test_schema_and_docs_available(self):
        schema = self.client.get("/api/schema/", {"format": "json"})
        self.assertEqual(schema.status_code, 200)
        self.assertEqual(self.client.get("/api/docs/").status_code, 200)
        self.assertEqual(self.client.get("/api/redoc/").status_code, 200)
