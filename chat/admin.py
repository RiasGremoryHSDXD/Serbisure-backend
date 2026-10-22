from django.contrib import admin
from .models import AccountAccessAudit
from .access_audit import access_history
from .services import is_superadmin, jurisdiction


@admin.register(AccountAccessAudit)
class AccountAccessAuditAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor_name', 'action', 'target_name', 'target_barangay')
    list_filter = ('action', 'target_role')
    search_fields = ('actor_name', 'target_name', 'target_barangay')
    readonly_fields = tuple(field.name for field in AccountAccessAudit._meta.fields)
    actions = None

    def has_view_permission(self, request, obj=None):
        user = request.user
        return bool(user.is_active and not user.is_account_suspended
            and (is_superadmin(user) or (user.account_type == 'Barangay' and jurisdiction(user)))
            and super().has_view_permission(request, obj))

    def get_queryset(self, request):
        return access_history(request.user, {})

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
