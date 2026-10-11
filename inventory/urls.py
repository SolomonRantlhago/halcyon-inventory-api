from rest_framework.routers import DefaultRouter

from inventory import views

router = DefaultRouter()
router.register("suppliers", views.SupplierViewSet, basename="supplier")
router.register("warehouses", views.WarehouseViewSet, basename="warehouse")
router.register("products", views.ProductViewSet, basename="product")
router.register("stock-levels", views.StockLevelViewSet, basename="stocklevel")

urlpatterns = router.urls
