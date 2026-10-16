import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from .serializers import UserRegistrationSerializer
from .views import LoginThrottle, RegistrationThrottle, UserRegistrationView


@override_settings(CACHES={
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'registration-throttle-tests'},
})
class RegistrationThrottleTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        cache.clear()
        self.addCleanup(cache.clear)
        self.clock = self.enterContext(patch.object(RegistrationThrottle, 'timer', return_value=1000.0))
        self.serializer_class = self.enterContext(patch('accounts.views.UserRegistrationSerializer'))
        self.serializer = self.serializer_class.return_value
        self.serializer.is_valid.return_value = False
        self.serializer.errors = {
            'email': ['Enter a valid email address.'],
            'contact_number': ['Enter a valid mobile number.'],
            'first_name': ['This field is required.'],
        }

    def submit(self, key=None, data=None):
        request = self.factory.post('/api/v1/accounts/register/', data or {}, format='json',
                                    HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))
        return UserRegistrationView.as_view()(request)

    def test_invalid_submissions_keep_field_errors_and_never_create_accounts(self):
        for _ in range(5):
            response = self.submit()
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data, self.serializer.errors)
        self.serializer.save.assert_not_called()

    def test_real_validation_rejects_invalid_email_phone_and_missing_fields(self):
        # Keep real field validators while treating the account directory as empty.
        with patch('accounts.views.UserRegistrationSerializer', UserRegistrationSerializer), \
                patch('django.db.models.query.QuerySet.exists', return_value=False):
            for payload in ({}, {'email': 'invalid-email'}, {'contact_number': '123'}):
                response = self.submit(data=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn('email', response.data)
                self.assertIn('contact_number', response.data)
                self.assertNotIn('access', response.data)

    def test_sixth_attempt_has_five_minute_retry_header_and_clear_failure_copy(self):
        for _ in range(5):
            self.submit()
        response = self.submit()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '300')
        self.assertIn('No account was created by this attempt.', str(response.data['detail']))
        self.assertIn('5 minutes', str(response.data['detail']))
        self.assertNotIn('hours', str(response.data['detail']))
        self.serializer.save.assert_not_called()

    def test_retry_at_five_minute_boundary_is_allowed_and_blocked_calls_do_not_extend_it(self):
        for _ in range(5):
            self.submit()
        self.clock.return_value = 1299.0
        response = self.submit()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '1')
        self.clock.return_value = 1300.0
        self.assertEqual(self.submit().status_code, 400)
        self.serializer.save.assert_not_called()

    def test_login_or_old_daily_counter_does_not_block_registration(self):
        request = self.factory.post('/api/v1/accounts/register/')
        request.user = None
        login_key = LoginThrottle().get_cache_key(request, None)
        registration_key = RegistrationThrottle().get_cache_key(request, None)
        self.assertNotEqual(login_key, registration_key)
        cache.set(login_key, [1000.0] * 5, 86400)
        self.assertEqual(self.submit().status_code, 400)

    def test_confirmed_success_keeps_tokens_and_idempotent_replay(self):
        self.serializer.is_valid.return_value = True
        self.serializer.errors = {}
        token = self.enterContext(patch('accounts.views.CustomLoginSerializer.get_token')).return_value
        token.__str__.return_value = 'refresh-token'
        token.access_token = 'access-token'
        key = str(uuid.uuid4())
        first = self.submit(key)
        second = self.submit(key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data['access'], 'access-token')
        self.assertEqual(first.data['refresh'], 'refresh-token')
        self.assertEqual(first.data, second.data)
        self.serializer.save.assert_called_once()
