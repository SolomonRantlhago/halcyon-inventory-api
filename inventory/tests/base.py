from rest_framework.test import APITestCase

from accounts.models import User
from inventory.models import Product, StockLevel, Supplier, Warehouse


class InventoryTestCase(APITestCase):
    """Shared fixtures: an admin, two standard users and a small catalogue."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            "boss", "boss@example.com", "Str0ngPass!23", role=User.Role.ADMIN
        )
        cls.alice = User.objects.create_user("alice", "alice@example.com", "Str0ngPass!23")
        cls.bob = User.objects.create_user("bob", "bob@example.com", "Str0ngPass!23")

        cls.supplier = Supplier.objects.create(name="Acme", email="a@acme.example")
        cls.other_supplier = Supplier.objects.create(name="Globex", email="g@globex.example")
        cls.warehouse = Warehouse.objects.create(name="Main", code="MAIN", city="Joburg")
        cls.product = Product.objects.create(
            sku="WIDGET-1", name="Widget", category="Hardware", unit_price="10.00",
            reorder_level=5,
        )
        cls.product.suppliers.add(cls.supplier)
        cls.unsupplied = Product.objects.create(
            sku="GADGET-1", name="Gadget", category="Hardware", unit_price="5.00"
        )
        cls.unsupplied.suppliers.add(cls.other_supplier)
        cls.stock = StockLevel.objects.create(
            product=cls.product, warehouse=cls.warehouse, quantity=3
        )

    def as_admin(self):
        self.client.force_authenticate(self.admin)

    def as_alice(self):
        self.client.force_authenticate(self.alice)

    def order_payload(self, **overrides):
        payload = {
            "supplier": self.supplier.pk,
            "warehouse": self.warehouse.pk,
            "notes": "Restock",
            "items": [{"product": self.product.pk, "quantity": 10}],
        }
        payload.update(overrides)
        return payload
