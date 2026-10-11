from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from core.exceptions import ConflictError
from inventory.models import (
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    StockLevel,
    Supplier,
    Warehouse,
)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "email", "phone", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ["id", "name", "code", "city", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def to_internal_value(self, data):
        # Normalise before field validators run so "jhb1" is accepted as "JHB1".
        data = data.copy()
        if isinstance(data.get("code"), str):
            data["code"] = data["code"].strip().upper()
        return super().to_internal_value(data)


class ProductSerializer(serializers.ModelSerializer):
    suppliers = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Supplier.objects.all(), required=False
    )
    total_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "category", "unit_price", "reorder_level",
            "is_active", "suppliers", "total_stock", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "total_stock", "created_at", "updated_at"]

    def get_total_stock(self, obj) -> int:
        annotated = getattr(obj, "total_stock", None)
        if annotated is not None:
            return annotated
        return obj.stock_levels.aggregate(total=Sum("quantity"))["total"] or 0

    def to_internal_value(self, data):
        data = data.copy()
        if isinstance(data.get("sku"), str):
            data["sku"] = data["sku"].strip().upper()
        return super().to_internal_value(data)

    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Unit price must be greater than zero.")
        return value


class StockLevelSerializer(serializers.ModelSerializer):
    is_low = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockLevel
        fields = [
            "id", "product", "warehouse", "quantity", "is_low", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "is_low", "created_at", "updated_at"]


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    unit_cost = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal("0")
    )
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = ["id", "product", "quantity", "unit_cost", "line_total"]
        read_only_fields = ["id", "line_total"]
        # Duplicate products are rejected in PurchaseOrderSerializer.validate.
        validators = []


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "reference", "supplier", "warehouse", "status", "notes",
            "created_by", "items", "total", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "reference", "status", "created_by", "total", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        supplier = attrs.get("supplier") or (self.instance.supplier if self.instance else None)
        items = attrs.get("items")

        if items is not None and not items:
            raise serializers.ValidationError({"items": "At least one item is required."})

        if items is None and self.instance is not None:
            products = [item.product for item in self.instance.items.all()]
        else:
            products = [item["product"] for item in (items or [])]

        ids = [product.pk for product in products]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError({"items": "Each product may appear only once."})

        if supplier is not None and not supplier.is_active:
            raise serializers.ValidationError({"supplier": "Supplier is inactive."})

        unsupplied = [
            p.sku for p in products if not p.suppliers.filter(pk=supplier.pk).exists()
        ]
        if unsupplied:
            raise serializers.ValidationError(
                {"items": f"Not supplied by {supplier.name}: {', '.join(unsupplied)}."}
            )
        return attrs

    @staticmethod
    def _create_items(order, items):
        PurchaseOrderItem.objects.bulk_create(
            PurchaseOrderItem(
                order=order,
                product=item["product"],
                quantity=item["quantity"],
                unit_cost=item.get("unit_cost", item["product"].unit_price),
            )
            for item in items
        )

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop("items")
        order = PurchaseOrder.objects.create(**validated_data)
        self._create_items(order, items)
        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != PurchaseOrder.Status.PENDING:
            raise ConflictError("Only pending orders can be edited.")
        items = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            self._create_items(instance, items)
        return instance
