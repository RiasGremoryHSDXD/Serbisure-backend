"""Guard against accidentally routing the staging deployment to production."""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from scripts.start_railway import validate_environment


class RailwayEnvironmentTests(SimpleTestCase):
    def setUp(self):
        self.env = {
            'DATABASE_URL': 'postgresql://test:test@example.test/staging-environment?sslmode=require',
            'REDIS_URL': 'redis://test:test@redis.railway.internal:6379/0',
            'SECRET_KEY': 'test-only-key', 'DJANGO_DEBUG': 'false',
            'REALTIME_ALLOWED_ORIGINS': 'https://staging.example.test', 'PORT': '9000',
        }

    def test_accepts_staging_database_and_injected_port(self):
        self.assertEqual(validate_environment(self.env), 9000)

    def test_rejects_production_or_missing_database(self):
        for value in ('', 'postgresql://test:test@example.test/serbisure-production-db'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_environment({**self.env, 'DATABASE_URL': value})

    def test_requires_external_redis_and_explicit_runtime_settings(self):
        for key, value in (('REDIS_URL', ''), ('REDIS_URL', 'redis://127.0.0.1:6379/0'),
                           ('SECRET_KEY', ''), ('DJANGO_DEBUG', 'true'),
                           ('REALTIME_ALLOWED_ORIGINS', ''), ('PORT', '0')):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_environment({**self.env, key: value})


@override_settings(REDIS_URL='redis://test.invalid/0')
class ReadinessTests(SimpleTestCase):
    def test_healthy_when_database_and_redis_respond(self):
        with patch('core.health.connection') as database, patch('core.health.Redis') as redis:
            database.cursor.return_value.__enter__.return_value = MagicMock()
            response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
        redis.from_url.return_value.__enter__.return_value.ping.assert_called_once()
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_dependency_failure_is_unavailable_without_exposing_credentials(self):
        with patch('core.health.connection') as database:
            database.cursor.side_effect = RuntimeError('private connection detail')
            response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})

    def test_redis_failure_is_unavailable(self):
        with patch('core.health.connection'), patch('core.health.Redis') as redis:
            redis.from_url.return_value.__enter__.return_value.ping.side_effect = OSError('unreachable')
            self.assertEqual(self.client.get('/api/health/').status_code, 503)
