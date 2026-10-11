from django.db.models import Sum
from rest_framework import serializers

from inventory.models import Product, StockLevel, Supplier, Warehouse


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
