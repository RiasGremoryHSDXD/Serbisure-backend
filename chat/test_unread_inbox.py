from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from unittest.mock import patch
from rest_framework.test import APIClient

from chat.models import tbl_chat_message

User = get_user_model()


class PortalUnreadInboxTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = User.objects.create_user(username='portaladmin', email='admin@example.test', password='Password123!', contact_number='+639123456701', account_type='Admin', is_staff=True, is_superuser=True)
        self.officer = User.objects.create_user(username='portalofficer', email='officer@example.test', password='Password123!', contact_number='+639123456702', account_type='Barangay', barangay='Agusan')
        self.home = User.objects.create_user(username='home', email='home@example.test', password='Password123!', contact_number='+639123456703', account_type='Homeowner', barangay='Agusan')
        self.worker = User.objects.create_user(username='worker', email='worker@example.test', password='Password123!', contact_number='+639123456704', account_type='Kasambahay', barangay='Agusan')

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

    def test_reply_previews_exclude_quote_metadata_for_text_and_photos(self):
        for message_type in ('text', 'image'):
            with self.subTest(message_type=message_type):
                tbl_chat_message.objects.create(sender_id=self.admin, receiver_id=self.home,
                    message_type=message_type,
                    message_payload=f'> [Homeowner|https://example.test/photo.jpg|{self.home.pk}]: 📷 Photo\n\nHere is my reply')
                preview = self.inbox(self.home)[str(self.admin.pk)]['last_message']
                self.assertIn('Here is my reply', preview)
                self.assertNotIn('https://', preview)
                self.assertNotIn('Homeowner|', preview)

    def test_photo_reply_caption_accepts_metadata_within_the_text_message_limit(self):
        from chat.serializers import SendImageMessageSerializer
        from rest_framework.exceptions import ValidationError
        field = SendImageMessageSerializer().fields['message_payload']
        caption = '> [Homeowner|https://example.test/' + 'a' * 180 + '|message-id]: 📷 Photo\n\nMy photo reply'
        self.assertEqual(field.run_validation(caption), caption)
        with self.assertRaises(ValidationError):
            field.run_validation('a' * 501)

    def thread_ids(self, user, partner):
        self.client.force_authenticate(user=user)
        response = self.client.get(f'/api/v1/chat/thread/{partner.pk}/')
        self.assertEqual(response.status_code, 200, response.data)
        messages = response.data.get('data', response.data.get('results', []))
        return {str(message['chat_message_id']) for message in messages}

    def test_removal_is_private_and_keeps_text_and_media_for_every_account_role(self):
        for actor in (self.admin, self.officer, self.home, self.worker):
            partner = self.home if actor in (self.admin, self.officer, self.worker) else self.worker
            for outgoing in (True, False):
                with self.subTest(role=actor.account_type, outgoing=outgoing):
                    sender, receiver = (actor, partner) if outgoing else (partner, actor)
                    message = self.message(sender, receiver, message_type='image', image_public_id='receipts/evidence')
                    self.client.force_authenticate(user=actor)
                    for _ in range(2):
                        response = self.client.delete(f'/api/v1/chat/message/{message.pk}/')
                        self.assertEqual(response.status_code, 200, response.data)
                    message.refresh_from_db()
                    self.assertFalse(message.is_deleted)
                    self.assertEqual(message.message_payload, 'Hello')
                    self.assertEqual(message.image_public_id, 'receipts/evidence')
                    self.assertEqual(message.hidden_by_sender, outgoing)
                    self.assertEqual(message.hidden_by_receiver, not outgoing)
                    # Fresh authenticated requests represent reopening or another device.
                    self.assertNotIn(str(message.pk), self.thread_ids(actor, partner))
                    self.assertIn(str(message.pk), self.thread_ids(partner, actor))

    def test_private_removal_updates_only_own_inbox_and_unread_count(self):
        older = self.message(self.home, self.admin)
        newer = tbl_chat_message.objects.create(sender_id=self.home, receiver_id=self.admin, message_payload='New receipt')
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.delete(f'/api/v1/chat/message/{newer.pk}/').status_code, 200)
        own = self.inbox(self.admin)[str(self.home.pk)]
        self.assertEqual(own['unread_count'], 1)
        self.assertEqual(own['last_message'], older.message_payload)
        other = self.inbox(self.home)[str(self.admin.pk)]
        self.assertEqual(other['last_message'], 'You: New receipt')
        self.thread_ids(self.admin, self.home)
        newer.refresh_from_db()
        self.assertFalse(newer.is_read, 'Opening a thread must not mark hidden messages as read')

    def test_removing_all_messages_hides_only_own_inbox_entry(self):
        message = self.message(self.home, self.admin)
        self.client.force_authenticate(user=self.admin)
        self.client.delete(f'/api/v1/chat/message/{message.pk}/')
        self.assertEqual(self.inbox(self.admin), {})
        self.assertIn(str(self.admin.pk), self.inbox(self.home))

    def test_other_participant_can_still_react_after_removal(self):
        message = self.message(self.home, self.admin)
        self.client.force_authenticate(user=self.admin)
        self.client.delete(f'/api/v1/chat/message/{message.pk}/')
        self.client.force_authenticate(user=self.home)
        self.assertEqual(self.client.post(f'/api/v1/chat/react/{message.pk}/', {'emoji': '👍'}, format='json').status_code, 200)

    def test_unrelated_or_unauthenticated_account_cannot_remove(self):
        message = self.message(self.home, self.admin)
        self.assertIn(self.client.delete(f'/api/v1/chat/message/{message.pk}/').status_code, (401, 403))
        self.client.force_authenticate(user=self.worker)
        self.assertEqual(self.client.delete(f'/api/v1/chat/message/{message.pk}/').status_code, 403)
        message.refresh_from_db()
        self.assertFalse(message.hidden_by_sender)
        self.assertFalse(message.hidden_by_receiver)
        self.assertFalse(message.is_deleted)

    def test_removal_notifies_only_the_removing_accounts_devices(self):
        message = self.message(self.home, self.admin)
        self.client.force_authenticate(user=self.admin)
        with patch('realtime.events.publish') as publish:
            self.client.delete(f'/api/v1/chat/message/{message.pk}/')
        publish.assert_called_once_with([self.admin.pk], {
            'type': 'chat.changed', 'partner_id': str(self.home.pk), 'message_id': str(message.pk),
        })
