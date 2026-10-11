from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import ConflictError
from core.permissions import IsAdmin, IsAdminOrReadOnly, IsOwnerOrAdmin, is_admin
from inventory.models import Product, PurchaseOrder, StockLevel, Supplier, Warehouse
from inventory.serializers import (
    ProductSerializer,
    PurchaseOrderSerializer,
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


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    search_fields = ["reference", "notes"]
    ordering_fields = ["created_at", "status"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PurchaseOrder.objects.none()  # schema generation has no real user
        qs = PurchaseOrder.objects.select_related(
            "supplier", "warehouse", "created_by"
        ).prefetch_related("items__product")
        if not is_admin(self.request.user):
            qs = qs.filter(created_by=self.request.user)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def get_permissions(self):
        if self.action in ("approve", "receive"):
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated(), IsOwnerOrAdmin()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.status != PurchaseOrder.Status.PENDING:
            raise ConflictError("Only pending orders can be deleted; cancel it instead.")
        instance.delete()

    def _transition(self, request, method_name):
        order = self.get_object()
        getattr(order, method_name)()
        order = self.get_queryset().get(pk=order.pk)
        return Response(self.get_serializer(order).data, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Admin: pending -> approved."""
        return self._transition(request, "approve")

    @extend_schema(request=None, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        """Admin: approved -> received, adding stock to the destination warehouse."""
        return self._transition(request, "receive")

    @extend_schema(request=None, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Owner or admin: pending/approved -> cancelled."""
        return self._transition(request, "cancel")
