from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import User


@admin.register(User)
class InventoryUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Inventory", {"fields": ("role",)}),)
    list_display = ("username", "email", "role", "is_staff")
    list_filter = UserAdmin.list_filter + ("role",)
