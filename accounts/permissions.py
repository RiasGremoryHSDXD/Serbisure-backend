from rest_framework.permissions import BasePermission

class IsPortalAdmin(BasePermission):
    message = 'Only administrators and barangay officers can access this resource.'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and
                    (user.account_type in ['Admin', 'Barangay'] or user.is_staff or user.is_superuser))

class IsPortalSuperadmin(IsPortalAdmin):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.account_type != 'Barangay'

class IsKasambahay(BasePermission):
    """
    Allows access only to authenticated users with account_type == 'Kasambahay'.
    Returns 403 Forbidden for other account types (e.g. Homeowner, Admin, Barangay).
    """
    message = "Only Kasambahay accounts can access this resource."

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            getattr(request.user, 'account_type', None) == 'Kasambahay'
        )
