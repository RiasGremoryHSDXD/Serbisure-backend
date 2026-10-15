from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from chat.models import tbl_chat_message

User = get_user_model()


class PortalUnreadInboxTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = User.objects.create_user(username='portaladmin', email='admin@example.test', password='Password123!', contact_number='+639123456701', account_type='Admin', is_staff=True, is_superuser=True)
        self.officer = User.objects.create_user(username='portalofficer', email='officer@example.test', password='Password123!', contact_number='+639123456702', account_type='Barangay', barangay='Agusan')
        self.home = User.objects.create_user(username='home', email='home@example.test', password='Password123!', contact_number='+639123456703', account_type='Homeowner')
        self.worker = User.objects.create_user(username='worker', email='worker@example.test', password='Password123!', contact_number='+639123456704', account_type='Kasambahay')

    def message(self, sender, receiver, **kwargs):
        return tbl_chat_message.objects.create(sender_id=sender, receiver_id=receiver, message_payload='Hello', **kwargs)

    def inbox(self, user):
        self.client.force_authenticate(user=user)
        response = self.client.get('/api/v1/chat/inbox/')
        self.assertEqual(response.status_code, 200)
        return {entry['partner_id']: entry for entry in response.data['data']}

    def test_counts_only_received_live_unread_messages_for_both_portal_roles(self):
        for recipient in (self.admin, self.officer):
            with self.subTest(account_type=recipient.account_type):
                self.message(self.home, recipient)
                self.message(self.home, recipient, message_type='image')
                self.message(self.worker, recipient)
                self.message(self.home, recipient, is_read=True)
                self.message(self.home, recipient, is_deleted=True)
                self.message(recipient, self.home)
                inbox = self.inbox(recipient)
                self.assertEqual(inbox[str(self.home.id)]['unread_count'], 2)
                self.assertEqual(inbox[str(self.worker.id)]['unread_count'], 1)

    def test_inbox_poll_does_not_mark_messages_read(self):
        msg = self.message(self.home, self.admin)
        self.inbox(self.admin)
        self.inbox(self.admin)
        msg.refresh_from_db()
        self.assertFalse(msg.is_read)

    def test_open_thread_clears_only_this_recipient_and_partner(self):
        for recipient in (self.admin, self.officer):
            with self.subTest(account_type=recipient.account_type):
                home_msg = self.message(self.home, recipient)
                worker_msg = self.message(self.worker, recipient)
                outgoing = self.message(recipient, self.home)
                self.client.force_authenticate(user=recipient)
                response = self.client.get(f'/api/v1/chat/thread/{self.home.id}/')
                self.assertEqual(response.status_code, 200)
                home_msg.refresh_from_db(); worker_msg.refresh_from_db(); outgoing.refresh_from_db()
                self.assertTrue(home_msg.is_read)
                self.assertFalse(worker_msg.is_read)
                self.assertFalse(outgoing.is_read)
                inbox = self.inbox(recipient)
                self.assertEqual(inbox[str(self.home.id)]['unread_count'], 0)
                self.assertEqual(inbox[str(self.worker.id)]['unread_count'], 1)

    def test_different_portal_account_cannot_read_another_account_messages(self):
        msg = self.message(self.home, self.admin)
        self.assertEqual(self.inbox(self.officer), {})
        self.client.get(f'/api/v1/chat/thread/{self.home.id}/')
        msg.refresh_from_db()
        self.assertFalse(msg.is_read)

    def test_inbox_requires_authentication(self):
        self.message(self.home, self.admin)
        self.assertIn(self.client.get('/api/v1/chat/inbox/').status_code, (401, 403))
