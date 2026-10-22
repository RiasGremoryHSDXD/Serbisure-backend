from django.contrib import admin
from .penalty_models import PenaltyAdjustment
from .penalty_management import adjustment_history, assert_official
from rest_framework.exceptions import PermissionDenied


@admin.register(PenaltyAdjustment)
class PenaltyAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user_name', 'user_barangay', 'points_delta', 'admin_name', 'report_verified')
    readonly_fields = tuple(field.name for field in PenaltyAdjustment._meta.fields)
    actions = None

    def get_queryset(self, request):
        return adjustment_history(request.user)

    def has_view_permission(self, request, obj=None):
        try:
            assert_official(request.user)
        except PermissionDenied:
            return False
        return super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
