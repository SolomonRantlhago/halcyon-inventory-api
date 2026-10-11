from django.contrib import admin

from inventory import models


class PurchaseOrderItemInline(admin.TabularInline):
    model = models.PurchaseOrderItem
    extra = 0


@admin.register(models.PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "supplier", "warehouse", "status", "created_by")
    list_filter = ("status",)
    inlines = [PurchaseOrderItemInline]


admin.site.register(models.Supplier)
admin.site.register(models.Warehouse)
admin.site.register(models.Product)
admin.site.register(models.StockLevel)
