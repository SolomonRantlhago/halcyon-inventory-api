import uuid

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction

from core.exceptions import ConflictError

SKU_VALIDATOR = RegexValidator(
    r"^[A-Z0-9][A-Z0-9-]{2,31}$",
    "SKU must be 3-32 characters: uppercase letters, digits and hyphens.",
)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Supplier(TimeStampedModel):
    name = models.CharField(max_length=150, unique=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Warehouse(TimeStampedModel):
    name = models.CharField(max_length=150)
    code = models.CharField(
        max_length=10,
        unique=True,
        validators=[RegexValidator(r"^[A-Z0-9]{2,10}$", "Use 2-10 uppercase letters/digits.")],
    )
    city = models.CharField(max_length=100)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Product(TimeStampedModel):
    sku = models.CharField(max_length=32, unique=True, validators=[SKU_VALIDATOR])
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    reorder_level = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    suppliers = models.ManyToManyField(Supplier, related_name="products", blank=True)

    class Meta:
        ordering = ["sku"]
        indexes = [
            models.Index(fields=["name"], name="product_name_idx"),
            models.Index(fields=["category", "name"], name="product_category_name_idx"),
        ]

    def __str__(self):
        return f"{self.sku} ({self.name})"


class StockLevel(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_levels")
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="stock_levels"
    )
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["warehouse__code", "product__sku"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "warehouse"], name="unique_product_per_warehouse"
            )
        ]
        indexes = [models.Index(fields=["warehouse", "quantity"], name="stock_wh_qty_idx")]

    @property
    def is_low(self):
        return self.quantity <= self.product.reorder_level

    def __str__(self):
        return f"{self.product.sku} @ {self.warehouse.code}: {self.quantity}"


class PurchaseOrder(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    ALLOWED_TRANSITIONS = {
        Status.PENDING: {Status.APPROVED, Status.CANCELLED},
        Status.APPROVED: {Status.RECEIVED, Status.CANCELLED},
    }

    reference = models.CharField(max_length=20, unique=True, editable=False)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="po_status_created_idx"),
            models.Index(fields=["created_by", "status"], name="po_user_status_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"PO-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    @property
    def total(self):
        return sum(item.line_total for item in self.items.all())

    def _move_to(self, target):
        """Lock the row and apply a state transition if the state machine allows it."""
        with transaction.atomic():
            locked = PurchaseOrder.objects.select_for_update().get(pk=self.pk)
            if target not in self.ALLOWED_TRANSITIONS.get(locked.status, set()):
                raise ConflictError(
                    f"Cannot move a {locked.status} order to {target}."
                )
            locked.status = target
            locked.save(update_fields=["status", "updated_at"])
            self.status = target
            self.updated_at = locked.updated_at
            return locked

    def approve(self):
        self._move_to(self.Status.APPROVED)

    def cancel(self):
        self._move_to(self.Status.CANCELLED)

    def receive(self):
        """Mark as received and add every line's quantity to the destination warehouse."""
        with transaction.atomic():
            locked = self._move_to(self.Status.RECEIVED)
            for item in locked.items.select_related("product"):
                stock = (
                    StockLevel.objects.select_for_update()
                    .filter(product=item.product, warehouse=locked.warehouse)
                    .first()
                )
                if stock is None:
                    stock = StockLevel(product=item.product, warehouse=locked.warehouse)
                stock.quantity += item.quantity
                stock.save()

    def __str__(self):
        return self.reference


class PurchaseOrderItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="unique_product_per_order")
        ]

    @property
    def line_total(self):
        return self.quantity * self.unit_cost

    def __str__(self):
        return f"{self.order.reference}: {self.quantity} x {self.product.sku}"
