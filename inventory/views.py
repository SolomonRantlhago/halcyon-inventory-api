from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from core.permissions import IsAdminOrReadOnly
from inventory.models import Product, StockLevel, Supplier, Warehouse
from inventory.serializers import (
    ProductSerializer,
    StockLevelSerializer,
    SupplierSerializer,
    WarehouseSerializer,
)


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["name", "email"]
    ordering_fields = ["name", "created_at"]


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["name", "code", "city"]
    ordering_fields = ["code", "name", "created_at"]


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["sku", "name", "category"]
    ordering_fields = ["sku", "name", "unit_price", "created_at", "total_stock"]

    def get_queryset(self):
        qs = Product.objects.prefetch_related("suppliers").annotate(
            total_stock=Coalesce(Sum("stock_levels__quantity"), 0)
        )
        params = self.request.query_params
        if params.get("category"):
            qs = qs.filter(category__iexact=params["category"])
        if params.get("supplier"):
            qs = qs.filter(suppliers__id=params["supplier"])
        return qs.order_by("sku")

    @extend_schema(responses=ProductSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        """Active products whose total stock is at or below their reorder level."""
        qs = self.filter_queryset(self.get_queryset()).filter(
            is_active=True, total_stock__lte=F("reorder_level")
        )
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class StockLevelViewSet(viewsets.ModelViewSet):
    serializer_class = StockLevelSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["product__sku", "product__name", "warehouse__code"]
    ordering_fields = ["quantity", "updated_at"]

    def get_queryset(self):
        qs = StockLevel.objects.select_related("product", "warehouse")
        params = self.request.query_params
        if params.get("warehouse"):
            qs = qs.filter(warehouse_id=params["warehouse"])
        if params.get("product"):
            qs = qs.filter(product_id=params["product"])
        return qs
