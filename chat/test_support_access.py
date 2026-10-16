import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from .models import tbl_chat_message
from .services import can_chat, support_contacts

User = get_user_model()


class SupportChatAccessTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.sequence = 0
        self.admin = self.account('Admin', '', is_superuser=True, is_staff=True)
        self.other_admin = self.account('Admin', '', is_staff=True)
        self.desk = self.account('Barangay', 'Pagatpat')
        self.other_desk = self.account('Barangay', 'Carmen')
        self.inactive_desk = self.account('Barangay', 'Bulua', is_active=False)
        self.home = self.account('Homeowner', 'Pagatpat')
        self.worker = self.account('Kasambahay', 'Brgy. pAgAtPaT')
        self.outsider = self.account('Homeowner', 'Carmen', street='Near Pagatpat')

    def account(self, role, barangay, **extra):
        self.sequence += 1
        extra.setdefault('city', 'City of Cagayan De Oro')
        extra.setdefault('province', 'Misamis Oriental')
        return User.objects.create_user(
            username=f'support-{self.sequence}', email=f'support-{self.sequence}@example.test',
            password='StrongPassword123!', contact_number=f'+63914444{self.sequence:04}',
            account_type=role, barangay=barangay, first_name='Test', last_name='User', **extra,
        )

    def send(self, sender, recipient, key=None):
        self.client.force_authenticate(sender)
        return self.client.post('/api/v1/chat/send/', {
            'receiver_id': str(recipient.pk), 'message_payload': 'Please help me with my account.',
        }, format='json', HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def message(self, sender, recipient):
        return tbl_chat_message.objects.create(sender_id=sender, receiver_id=recipient, message_payload='Existing message')

    def test_contacts_are_available_before_any_conversation_and_ignore_forged_location(self):
        for resident in (self.home, self.worker):
            self.client.force_authenticate(resident)
            response = self.client.get('/api/v1/chat/support-contacts/', {'barangay': 'Carmen'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual({contact['id'] for contact in response.data['superadmins']}, {str(self.admin.pk), str(self.other_admin.pk)})
            self.assertTrue(response.data['barangay']['available'])
            self.assertEqual([contact['id'] for contact in response.data['barangay']['contacts']], [str(self.desk.pk)])
            self.assertNotIn('email', response.data['superadmins'][0])
            self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertFalse(tbl_chat_message.objects.exists())

    def test_inactive_missing_and_unassigned_desks_return_support_fallback(self):
        for barangay in ('Bulua', 'No registered desk', ''):
            resident = self.account('Kasambahay', barangay)
            data = support_contacts(resident)
            self.assertFalse(data['barangay']['available'])
            self.assertEqual(data['barangay']['contacts'], [])
            self.assertIn('SerbiSure Support', data['barangay']['message'])
            self.assertTrue(data['superadmins'])
            self.assertEqual(self.send(resident, self.admin).status_code, 201)
        self.assertEqual(self.send(self.home, self.inactive_desk).status_code, 403)

    def test_both_mobile_roles_can_initiate_support_and_their_desk_and_receive_replies(self):
        for resident in (self.home, self.worker):
            for recipient in (self.admin, self.desk):
                with self.subTest(role=resident.account_type, recipient=recipient.account_type):
                    self.assertEqual(self.send(resident, recipient).status_code, 201)
                    self.client.force_authenticate(recipient)
                    inbox = self.client.get('/api/v1/chat/inbox/').data['data']
                    self.assertEqual(next(row for row in inbox if row['partner_id'] == str(resident.pk))['unread_count'], 1)
                    self.assertEqual(self.send(recipient, resident).status_code, 201)

    def test_cross_barangay_text_images_and_typing_are_denied_in_both_directions(self):
        for sender, recipient in ((self.home, self.other_desk), (self.other_desk, self.home), (self.desk, self.outsider), (self.desk, self.other_desk)):
            with self.subTest(sender=sender.pk, recipient=recipient.pk):
                self.assertEqual(self.send(sender, recipient).status_code, 403)
                self.assertEqual(self.client.post('/api/v1/chat/typing/', {'partner_id': str(recipient.pk), 'is_typing': True}, format='json').status_code, 403)
                with patch('cloudinary.uploader.upload') as upload:
                    response = self.client.post('/api/v1/chat/send-image/', {'receiver_id': str(recipient.pk)}, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
                    self.assertEqual(response.status_code, 403)
                    upload.assert_not_called()
        self.assertFalse(tbl_chat_message.objects.exists())

    @patch('cloudinary.uploader.upload', return_value={'public_id': 'support/photo', 'width': 50, 'height': 50})
    def test_own_desk_can_receive_images(self, upload):
        self.client.force_authenticate(self.home)
        image = SimpleUploadedFile('test.jpg', b'\xff\xd8\xff' + b'0' * 30, content_type='image/jpeg')
        response = self.client.post('/api/v1/chat/send-image/', {'receiver_id': str(self.desk.pk), 'image': image}, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201, response.data)
        upload.assert_called_once()

    def test_legacy_cross_barangay_messages_are_hidden_and_cannot_be_read_or_modified(self):
        incoming = self.message(self.outsider, self.desk)
        outgoing = self.message(self.desk, self.outsider)
        self.client.force_authenticate(self.desk)
        self.assertEqual(self.client.get('/api/v1/chat/inbox/').data['data'], [])
        self.assertEqual(self.client.get(f'/api/v1/chat/thread/{self.outsider.pk}/').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/v1/chat/read/{incoming.pk}/', {'is_read': True}, format='json').status_code, 403)
        self.assertEqual(self.client.post(f'/api/v1/chat/react/{incoming.pk}/', {'emoji': '👍'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/api/v1/chat/message/{outgoing.pk}/').status_code, 403)
        incoming.refresh_from_db()
        outgoing.refresh_from_db()
        self.assertFalse(incoming.is_read)
        self.assertFalse(outgoing.is_deleted)

    def test_missing_and_conflicting_jurisdictions_fail_closed(self):
        self.home.city, self.desk.city = 'City A', 'City B'
        self.assertFalse(can_chat(self.home, self.desk))
        self.home.city, self.desk.city = '', ''
        self.home.province, self.desk.province = 'Province A', 'Province B'
        self.assertFalse(can_chat(self.home, self.desk))
        self.home.province, self.desk.province = '', ''
        self.home.barangay = ''
        self.assertFalse(can_chat(self.home, self.desk))
        self.assertTrue(can_chat(self.home, self.admin))
        self.home.barangay = 'Pagatpat Heights'
        self.assertFalse(can_chat(self.home, self.desk))

    def test_common_city_label_variants_do_not_hide_the_assigned_desk(self):
        self.worker.city = 'Cagayan de Oro City'
        self.worker.save(update_fields=['city'])
        self.assertTrue(can_chat(self.worker, self.desk))
        self.assertEqual(support_contacts(self.worker)['barangay']['contacts'], [self.desk])

    def test_cached_retry_cannot_bypass_updated_location_and_is_scoped_to_sender(self):
        key = str(uuid.uuid4())
        self.assertEqual(self.send(self.home, self.desk, key).status_code, 201)
        self.assertEqual(self.send(self.worker, self.desk, key).status_code, 201)
        self.assertEqual(tbl_chat_message.objects.count(), 2)
        self.home.barangay = 'Carmen'
        self.home.save(update_fields=['barangay'])
        self.assertEqual(self.send(self.home, self.desk, key).status_code, 403)
        self.assertEqual(tbl_chat_message.objects.count(), 2)

    def test_superadmin_only_sees_conversations_addressed_to_them(self):
        for sender, recipient in ((self.home, self.admin), (self.worker, self.desk), (self.outsider, self.other_admin)):
            self.message(sender, recipient)
        self.client.force_authenticate(self.admin)
        inbox = self.client.get('/api/v1/chat/inbox/').data['data']
        self.assertEqual([row['partner_id'] for row in inbox], [str(self.home.pk)])
        self.assertEqual(self.client.get(f'/api/v1/chat/thread/{self.worker.pk}/').data['data'], [])
        self.assertFalse(tbl_chat_message.objects.get(sender_id=self.worker).is_read)

    def test_barangay_directory_ignores_other_barangay_filters_and_street_mentions(self):
        self.client.force_authenticate(self.desk)
        response = self.client.get('/api/v1/accounts/admin/users/', {'role': 'HOMEOWNER', 'barangay': 'Carmen'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data], [str(self.home.pk)])
        self.client.force_authenticate(self.home)
        self.assertEqual(self.client.get('/api/v1/accounts/admin/users/').status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/v1/accounts/admin/users/').status_code, 401)

    def test_support_discovery_requires_authenticated_resident(self):
        self.assertEqual(self.client.get('/api/v1/chat/support-contacts/').status_code, 401)
        self.client.force_authenticate(self.desk)
        self.assertEqual(self.client.get('/api/v1/chat/support-contacts/').status_code, 403)
