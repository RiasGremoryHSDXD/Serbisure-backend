from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from .authentication import assert_account_available


class AccountTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        from rest_framework_simplejwt.settings import api_settings
        token = RefreshToken(attrs['refresh'])
        user = get_user_model().objects.filter(**{api_settings.USER_ID_FIELD: token[api_settings.USER_ID_CLAIM]}).first()
        if not user or not user.is_active:
            raise AuthenticationFailed('Account unavailable.')
        assert_account_available(user)
        return super().validate(attrs)


class AccountTokenRefreshView(TokenRefreshView):
    serializer_class = AccountTokenRefreshSerializer
