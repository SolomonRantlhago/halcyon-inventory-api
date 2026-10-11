from inventory.models import Product, PurchaseOrder, StockLevel, Supplier, Warehouse
from inventory.tests.base import InventoryTestCase


class AuthAndPermissionTests(InventoryTestCase):
    def test_anonymous_gets_standard_401_schema(self):
        response = self.client.get("/api/products/")
        self.assertEqual(response.status_code, 401)
        error = response.json()["error"]
        self.assertEqual(error["status"], 401)
        self.assertEqual(error["code"], "not_authenticated")
        self.assertEqual(error["path"], "/api/products/")
        self.assertEqual(set(error), {"status", "code", "message", "details", "path"})

    def test_standard_user_can_read_but_not_write_catalogue(self):
        self.as_alice()
        self.assertEqual(self.client.get("/api/products/").status_code, 200)
        self.assertEqual(self.client.get("/api/suppliers/").status_code, 200)
        self.assertEqual(self.client.get("/api/warehouses/").status_code, 200)
        self.assertEqual(self.client.get("/api/stock-levels/").status_code, 200)
        response = self.client.post(
            "/api/suppliers/", {"name": "New", "email": "n@x.example"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "permission_denied")

    def test_not_found_uses_error_schema(self):
        self.as_admin()
        response = self.client.get("/api/products/99999/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")


class SupplierWarehouseCrudTests(InventoryTestCase):
    def test_supplier_crud(self):
        self.as_admin()
        created = self.client.post(
            "/api/suppliers/", {"name": "Initech", "email": "i@x.example"}, format="json"
        )
        self.assertEqual(created.status_code, 201)
        url = f"/api/suppliers/{created.json()['id']}/"
        self.assertEqual(self.client.get(url).status_code, 200)
        patched = self.client.patch(url, {"phone": "0123"}, format="json")
        self.assertEqual(patched.json()["phone"], "0123")
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_supplier_validation_error_schema(self):
        self.as_admin()
        response = self.client.post(
            "/api/suppliers/", {"name": "Acme", "email": "not-an-email"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        error = response.json()["error"]
        self.assertEqual(error["code"], "validation_error")
        self.assertIn("email", error["details"])
        self.assertIn("name", error["details"])  # duplicate name

    def test_warehouse_crud_and_code_uppercased(self):
        self.as_admin()
        created = self.client.post(
            "/api/warehouses/", {"name": "Dock", "code": "dk1", "city": "Durban"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["code"], "DK1")
        url = f"/api/warehouses/{created.json()['id']}/"
        self.assertEqual(self.client.put(
            url, {"name": "Dock 2", "code": "DK1", "city": "Durban"}, format="json"
        ).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_delete_warehouse_in_use_is_409(self):
        PurchaseOrder.objects.create(
            supplier=self.supplier, warehouse=self.warehouse, created_by=self.alice
        )
        self.as_admin()
        response = self.client.delete(f"/api/warehouses/{self.warehouse.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "conflict")


class ProductTests(InventoryTestCase):
    def test_create_update_delete_product(self):
        self.as_admin()
        response = self.client.post(
            "/api/products/",
            {
                "sku": "bolt-9", "name": "Bolt", "category": "Fasteners",
                "unit_price": "0.50", "suppliers": [self.supplier.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["sku"], "BOLT-9")
        self.assertEqual(body["total_stock"], 0)
        url = f"/api/products/{body['id']}/"
        self.assertEqual(self.client.patch(
            url, {"reorder_level": 99}, format="json"
        ).json()["reorder_level"], 99)
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_price_must_be_positive(self):
        self.as_admin()
        response = self.client.post(
            "/api/products/",
            {"sku": "FREE-1", "name": "Free", "category": "X", "unit_price": "0"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("unit_price", response.json()["error"]["details"])

    def test_bad_sku_rejected(self):
        self.as_admin()
        response = self.client.post(
            "/api/products/",
            {"sku": "!!", "name": "Bad", "category": "X", "unit_price": "1.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_list_filter_search_and_total_stock(self):
        self.as_alice()
        listing = self.client.get("/api/products/", {"category": "hardware"}).json()
        self.assertEqual(listing["count"], 2)
        widget = [p for p in listing["results"] if p["sku"] == "WIDGET-1"][0]
        self.assertEqual(widget["total_stock"], 3)
        found = self.client.get("/api/products/", {"search": "gadget"}).json()
        self.assertEqual(found["count"], 1)
        by_supplier = self.client.get(
            "/api/products/", {"supplier": self.supplier.pk}
        ).json()
        self.assertEqual(by_supplier["count"], 1)

    def test_low_stock_endpoint(self):
        self.as_alice()
        response = self.client.get("/api/products/low-stock/")
        self.assertEqual(response.status_code, 200)
        skus = {p["sku"] for p in response.json()["results"]}
        self.assertEqual(skus, {"WIDGET-1", "GADGET-1"})  # GADGET has 0 stock
        self.stock.quantity = 100
        self.stock.save()
        skus = {p["sku"] for p in self.client.get("/api/products/low-stock/").json()["results"]}
        self.assertEqual(skus, {"GADGET-1"})

    def test_delete_product_on_order_is_409(self):
        self.as_alice()
        self.client.post("/api/purchase-orders/", self.order_payload(), format="json")
        self.as_admin()
        response = self.client.delete(f"/api/products/{self.product.pk}/")
        self.assertEqual(response.status_code, 409)


class StockLevelTests(InventoryTestCase):
    def test_admin_crud_and_filters(self):
        self.as_admin()
        response = self.client.post(
            "/api/stock-levels/",
            {"product": self.unsupplied.pk, "warehouse": self.warehouse.pk, "quantity": 40},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["is_low"])
        url = f"/api/stock-levels/{response.json()['id']}/"
        self.assertEqual(self.client.patch(url, {"quantity": 1}, format="json").status_code, 200)
        by_product = self.client.get("/api/stock-levels/", {"product": self.product.pk}).json()
        self.assertEqual(by_product["count"], 1)
        by_wh = self.client.get("/api/stock-levels/", {"warehouse": self.warehouse.pk}).json()
        self.assertEqual(by_wh["count"], 2)
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_duplicate_pair_rejected(self):
        self.as_admin()
        response = self.client.post(
            "/api/stock-levels/",
            {"product": self.product.pk, "warehouse": self.warehouse.pk, "quantity": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_negative_quantity_rejected(self):
        self.as_admin()
        response = self.client.patch(
            f"/api/stock-levels/{self.stock.pk}/", {"quantity": -5}, format="json"
        )
        self.assertEqual(response.status_code, 400)


class PurchaseOrderTests(InventoryTestCase):
    def create_order(self):
        self.as_alice()
        response = self.client.post(
            "/api/purchase-orders/", self.order_payload(), format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_create_defaults_cost_and_owner(self):
        body = self.create_order()
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["created_by"], self.alice.pk)
        self.assertEqual(body["items"][0]["unit_cost"], "10.00")
        self.assertEqual(body["total"], "100.00")

    def test_rejects_product_not_supplied_by_supplier(self):
        self.as_alice()
        payload = self.order_payload(items=[{"product": self.unsupplied.pk, "quantity": 1}])
        response = self.client.post("/api/purchase-orders/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("items", response.json()["error"]["details"])

    def test_rejects_empty_duplicate_and_inactive(self):
        self.as_alice()
        for payload in (
            self.order_payload(items=[]),
            self.order_payload(items=[
                {"product": self.product.pk, "quantity": 1},
                {"product": self.product.pk, "quantity": 2},
            ]),
            self.order_payload(items=[{"product": self.product.pk, "quantity": 0}]),
        ):
            response = self.client.post("/api/purchase-orders/", payload, format="json")
            self.assertEqual(response.status_code, 400)
        Supplier.objects.filter(pk=self.supplier.pk).update(is_active=False)
        response = self.client.post(
            "/api/purchase-orders/", self.order_payload(), format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_standard_user_only_sees_own_orders(self):
        order = self.create_order()
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get("/api/purchase-orders/").json()["count"], 0)
        self.assertEqual(
            self.client.get(f"/api/purchase-orders/{order['id']}/").status_code, 404
        )
        self.as_admin()
        self.assertEqual(self.client.get("/api/purchase-orders/").json()["count"], 1)
        filtered = self.client.get("/api/purchase-orders/", {"status": "received"}).json()
        self.assertEqual(filtered["count"], 0)

    def test_edit_pending_order_and_replace_items(self):
        order = self.create_order()
        url = f"/api/purchase-orders/{order['id']}/"
        response = self.client.patch(
            url, {"items": [{"product": self.product.pk, "quantity": 2, "unit_cost": "9.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["total"], "18.00")
        response = self.client.patch(url, {"notes": "Updated"}, format="json")
        self.assertEqual(response.json()["notes"], "Updated")
        self.assertEqual(len(response.json()["items"]), 1)

    def test_only_admin_can_approve_and_receive(self):
        order = self.create_order()
        url = f"/api/purchase-orders/{order['id']}"
        self.assertEqual(self.client.post(f"{url}/approve/").status_code, 403)
        self.assertEqual(self.client.post(f"{url}/receive/").status_code, 403)

    def test_full_fulfilment_flow_updates_stock(self):
        order = self.create_order()
        url = f"/api/purchase-orders/{order['id']}"
        self.as_admin()
        premature = self.client.post(f"{url}/receive/")
        self.assertEqual(premature.status_code, 409)
        self.assertEqual(self.client.post(f"{url}/approve/").json()["status"], "approved")
        self.assertEqual(self.client.post(f"{url}/receive/").json()["status"], "received")
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 13)
        # Received orders are immutable.
        self.assertEqual(
            self.client.patch(f"{url}/", {"notes": "x"}, format="json").status_code, 409
        )
        self.assertEqual(self.client.delete(f"{url}/").status_code, 409)
        self.assertEqual(self.client.post(f"{url}/cancel/").status_code, 409)

    def test_owner_can_cancel_and_delete_pending(self):
        order = self.create_order()
        url = f"/api/purchase-orders/{order['id']}"
        self.assertEqual(self.client.post(f"{url}/cancel/").json()["status"], "cancelled")
        second = self.client.post(
            "/api/purchase-orders/", self.order_payload(), format="json"
        ).json()
        response = self.client.delete(f"/api/purchase-orders/{second['id']}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_other_user_cannot_cancel(self):
        order = self.create_order()
        self.client.force_authenticate(self.bob)
        response = self.client.post(f"/api/purchase-orders/{order['id']}/cancel/")
        self.assertEqual(response.status_code, 404)


class SmokeTests(InventoryTestCase):
    def test_counts_unchanged_by_reads(self):
        self.as_alice()
        self.client.get("/api/products/")
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(StockLevel.objects.count(), 1)
        self.assertEqual(Warehouse.objects.count(), 1)
