from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from realtime.presence import is_online, update_presence


@override_settings(REDIS_URL=None)
class PresenceLeaseTests(SimpleTestCase):
    def test_dead_connections_expire_even_without_a_disconnect_frame(self):
        with patch('realtime.presence.time.time', return_value=100):
            self.assertTrue(update_presence('expiry-user', 'connection', True))
        with patch('realtime.presence.time.time', return_value=166):
            self.assertFalse(is_online('expiry-user'))

    def test_heartbeat_extends_only_its_own_connection(self):
        with patch('realtime.presence.time.time', return_value=100):
            update_presence('lease-user', 'tab-one', True)
            update_presence('lease-user', 'tab-two', True)
        with patch('realtime.presence.time.time', return_value=140):
            update_presence('lease-user', 'tab-two', True)
        with patch('realtime.presence.time.time', return_value=166):
            self.assertTrue(is_online('lease-user'))
            self.assertFalse(update_presence('lease-user', 'tab-two', False))

    @override_settings(REDIS_URL='redis://unavailable.test')
    def test_redis_outage_is_unknown_rather_than_falsely_online_or_offline(self):
        with patch('realtime.presence.redis_client', side_effect=ConnectionError):
            self.assertIsNone(update_presence('outage-user', 'tab', True))
            self.assertIsNone(is_online('outage-user'))
