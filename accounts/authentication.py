from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication


def assert_account_available(user):
    if user.is_account_suspended:
        raise PermissionDenied({'code': 'account_suspended',
            'detail': 'Your account is suspended. Contact SerbiSure Support for assistance.'})


class AccountJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        assert_account_available(user)
        from .penalties import refresh_monthly_penalties
        refresh_monthly_penalties(user)
        return user
