from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.exceptions import ConflictError
from inventory.models import PurchaseOrder, PurchaseOrderItem, StockLevel, Warehouse
from inventory.tests.base import InventoryTestCase


class ModelTests(InventoryTestCase):
    def make_order(self, quantity=10):
        order = PurchaseOrder.objects.create(
            supplier=self.supplier, warehouse=self.warehouse, created_by=self.alice
        )
        PurchaseOrderItem.objects.create(
            order=order, product=self.product, quantity=quantity, unit_cost="2.50"
        )
        return order

    def test_str_methods(self):
        self.assertIn("WIDGET-1", str(self.product))
        self.assertEqual(str(self.supplier), "Acme")
        self.assertIn("MAIN", str(self.warehouse))
        self.assertIn("3", str(self.stock))
        order = self.make_order()
        self.assertEqual(str(order), order.reference)
        self.assertIn("WIDGET-1", str(order.items.first()))

    def test_sku_validation(self):
        self.product.sku = "bad sku!"
        with self.assertRaises(ValidationError):
            self.product.full_clean()

    def test_warehouse_code_validation(self):
        warehouse = Warehouse(name="X", code="lower", city="Y")
        with self.assertRaises(ValidationError):
            warehouse.full_clean()

    def test_stock_unique_per_product_and_warehouse(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockLevel.objects.create(
                product=self.product, warehouse=self.warehouse, quantity=1
            )

    def test_is_low_flag(self):
        self.assertTrue(self.stock.is_low)  # 3 <= reorder level 5
        self.stock.quantity = 50
        self.assertFalse(self.stock.is_low)

    def test_reference_generated_and_total(self):
        order = self.make_order(quantity=4)
        self.assertTrue(order.reference.startswith("PO-"))
        self.assertEqual(str(order.total), "10.00")

    def test_state_machine_happy_path_updates_stock(self):
        order = self.make_order(quantity=10)
        order.approve()
        order.receive()
        self.stock.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(self.stock.quantity, 13)

    def test_receive_creates_missing_stock_row(self):
        other = Warehouse.objects.create(name="Second", code="SEC", city="Cape Town")
        order = PurchaseOrder.objects.create(
            supplier=self.supplier, warehouse=other, created_by=self.alice
        )
        PurchaseOrderItem.objects.create(
            order=order, product=self.product, quantity=7, unit_cost="1.00"
        )
        order.approve()
        order.receive()
        self.assertEqual(
            StockLevel.objects.get(product=self.product, warehouse=other).quantity, 7
        )

    def test_invalid_transitions_raise_conflict(self):
        order = self.make_order()
        with self.assertRaises(ConflictError):
            order.receive()  # must be approved first
        order.cancel()
        with self.assertRaises(ConflictError):
            order.approve()
