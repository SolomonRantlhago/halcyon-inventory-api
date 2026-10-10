from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_admin(user):
    return bool(user and user.is_authenticated and user.is_inventory_admin)


class IsAdmin(BasePermission):
    message = "Administrator role required."

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsAdminOrReadOnly(BasePermission):
    """Any authenticated user may read; only admins may write."""

    message = "Administrator role required for this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return is_admin(request.user)


class IsOwnerOrAdmin(BasePermission):
    message = "You can only act on your own records."

    def has_object_permission(self, request, view, obj):
        return is_admin(request.user) or obj.created_by_id == request.user.id
