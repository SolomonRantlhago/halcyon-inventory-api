from rest_framework.test import APITestCase

from accounts.models import User


class AccountTests(APITestCase):
    def register(self, **overrides):
        data = {"username": "carol", "email": "carol@example.com", "password": "Str0ngPass!23"}
        data.update(overrides)
        return self.client.post("/api/auth/register/", data, format="json")

    def test_register_creates_standard_user_even_if_role_supplied(self):
        response = self.register(role="admin")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["role"], "standard")
        self.assertNotIn("password", response.json())

    def test_register_rejects_weak_password_and_duplicate_email(self):
        self.assertEqual(self.register(password="123").status_code, 400)
        self.register()
        duplicate = self.register(username="carol2")
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(duplicate.json()["error"]["code"], "validation_error")

    def test_jwt_login_refresh_and_me(self):
        self.register()
        tokens = self.client.post(
            "/api/auth/token/", {"username": "carol", "password": "Str0ngPass!23"}, format="json"
        ).json()
        self.assertIn("access", tokens)
        refreshed = self.client.post(
            "/api/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(refreshed.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.json()["username"], "carol")

    def test_bad_credentials_use_error_schema(self):
        response = self.client.post(
            "/api/auth/token/", {"username": "x", "password": "y"}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["status"], 401)

    def test_invalid_token_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)

    def test_superuser_always_has_admin_role(self):
        root = User.objects.create_superuser("root", "root@example.com", "Str0ngPass!23")
        self.assertEqual(root.role, User.Role.ADMIN)
        self.assertTrue(root.is_inventory_admin)
