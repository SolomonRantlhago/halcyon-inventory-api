from inventory.models import Product, PurchaseOrder, StockLevel, Warehouse
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


class SmokeTests(InventoryTestCase):
    def test_counts_unchanged_by_reads(self):
        self.as_alice()
        self.client.get("/api/products/")
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(StockLevel.objects.count(), 1)
        self.assertEqual(Warehouse.objects.count(), 1)
