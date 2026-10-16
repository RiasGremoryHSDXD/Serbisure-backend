from datetime import timedelta
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from .moderation import may_manage, restriction_until, set_suspension


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
