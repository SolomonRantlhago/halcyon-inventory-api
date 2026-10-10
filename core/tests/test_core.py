from unittest import mock
from rest_framework.test import APITestCase


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
