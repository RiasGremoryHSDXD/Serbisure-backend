from datetime import timedelta
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from .moderation import may_manage, restriction_until, set_suspension
from .access_audit import access_history
from .models import ACCESS_ACTIONS, AccountAccessAudit


class SuspensionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=['pause_chat', 'resume_chat', 'suspend_account', 'restore_account'])
    until = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if attrs['action'] == 'pause_chat':
            until, now = attrs.get('until'), timezone.now()
            if not until or not now < until <= now + timedelta(days=30):
                raise serializers.ValidationError({'until': 'Choose a future time within 30 days.'})
        elif 'until' in attrs:
            raise serializers.ValidationError({'until': 'Only a messaging pause accepts an expiry.'})
        return attrs


class SuspensionState(serializers.Serializer):
    chat_suspended_until = serializers.DateTimeField(read_only=True)
    is_account_suspended = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    suspended_by = serializers.PrimaryKeyRelatedField(read_only=True)
    can_manage = serializers.SerializerMethodField()

    def get_can_manage(self, obj):
        return may_manage(self.context['request'].user, obj)


class SuspensionThrottle(UserRateThrottle):
    scope = 'manual_suspension'
    rate = '60/hour'


class SafetyView(APIView):
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


class MySafetyView(SafetyView):
    def get(self, request):
        until = restriction_until(request.user)
        return Response({'restricted_until': until.isoformat() if until else None, 'support_available': True})


class UserSuspensionView(SafetyView):
    throttle_classes = [SuspensionThrottle]

    def get(self, request, user_id):
        target = get_object_or_404(get_user_model(), pk=user_id)
        if not may_manage(request.user, target):
            raise PermissionDenied('This account is outside your authority.')
        return Response(SuspensionState(target, context={'request': request}).data)

    def post(self, request, user_id):
        data = SuspensionInput(data=request.data)
        data.is_valid(raise_exception=True)
        target = set_suspension(request.user, user_id, **data.validated_data)
        return Response(SuspensionState(target, context={'request': request}).data)


class AccessHistoryQuery(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    barangay = serializers.CharField(required=False, allow_blank=True, max_length=255)
    action = serializers.ChoiceField(choices=ACCESS_ACTIONS, required=False)
    role = serializers.ChoiceField(choices=['Homeowner', 'Kasambahay'], required=False)
    user_id = serializers.UUIDField(required=False)


class AccessHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountAccessAudit
        fields = ['log_id', 'actor_id_snapshot', 'actor_name', 'actor_role', 'actor_barangay',
            'target_id_snapshot', 'target_name', 'target_role', 'target_barangay',
            'action', 'previous_state', 'new_state', 'created_at']
        read_only_fields = fields


class AccessHistoryPagination(PageNumberPagination):
    page_size = 5


class AccessHistoryView(SafetyView):
    """Read only. Entries are created exclusively by successful access changes."""
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        query = AccessHistoryQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        records = access_history(request.user, query.validated_data)
        pagination = AccessHistoryPagination()
        page = pagination.paginate_queryset(records, request, view=self)
        return pagination.get_paginated_response(AccessHistorySerializer(page, many=True).data)
