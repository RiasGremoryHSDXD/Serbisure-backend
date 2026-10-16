import uuid
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from .models import tbl_chat_message
from .moderation import assert_messaging_allowed, ChatSafetyError
from .moderation_rules import mask_text

User = get_user_model()


class MaskTests(SimpleTestCase):
    def test_required_examples_and_boundaries(self):
        for original, expected in [('kill', 'k*ll'), ('fuck you', 'f*ck you'), ('gago', 'g*go'), ('yawa', 'y*wa'),
                                   ('GAGO ka!', 'G*GO ka!'), ('patyon tika', 'p*tyon tika')]:
            self.assertEqual(mask_text(original), expected)
        for text in ['skill', 'killjoy', 'gagokabuhay', 'Please help me', 'Magkita ta ugma', 'ang balay', 'y*wa']:
            self.assertEqual(mask_text(text), text)

    def test_unicode_obfuscation_and_idempotence(self):
        for text in ['ｆｕｃｋ you', 'fu\u200bck you', 'f.u.c.k you', 'f_u_c_k you']:
            masked = mask_text(text)
            self.assertNotEqual(text, masked)
            self.assertEqual(mask_text(masked), masked)


class ManualSafetyTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.publish = patch('chat.moderation.publish').start()
        self.addCleanup(patch.stopall)
        self.owner = self.person('Homeowner')
        self.worker = self.person('Kasambahay')
        self.desk = self.person('Barangay')
        self.other_desk = self.person('Barangay', barangay='Carmen')
        self.admin = self.person('Admin')

    def person(self, role, **fields):
        n = User.objects.count() + 1
        values = dict(barangay='Pagatpat', city='City of Cagayan de Oro', province='Misamis Oriental')
        values.update(fields)
        return User.objects.create_user(email=f'user{n}@example.test', username=f'user{n}',
            password='TestPassword123!', account_type=role, first_name='Test', last_name='User',
            contact_number=f'+639{100000000+n:09}', **values)

    def action(self, actor, target, action='pause_chat', **fields):
        self.client.force_authenticate(actor)
        body = {'action': action, **fields}
        if action == 'pause_chat' and 'until' not in body:
            body['until'] = (timezone.now() + timedelta(hours=24)).isoformat()
        return self.client.post(f'/api/v1/chat/safety/users/{target.pk}/', body, format='json')

    def send(self, sender, recipient, text='Hello', key=None):
        self.client.force_authenticate(sender)
        return self.client.post('/api/v1/chat/send/', {'receiver_id': str(recipient.pk),
            'message_payload': text}, format='json', HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def test_mask_before_storage_notice_sender_only_and_no_penalty(self):
        result = self.send(self.owner, self.worker, 'fuck you gago yawa kill')
        self.assertEqual(result.status_code, 201, result.data)
        message = tbl_chat_message.objects.get()
        self.assertEqual(message.message_payload, 'f*ck you g*go y*wa k*ll')
        self.assertIn('communicate respectfully', result.data['language_warning'])
        self.owner.refresh_from_db()
        self.assertIsNone(self.owner.chat_suspended_until)
        self.assertFalse(self.owner.is_account_suspended)
        self.client.force_authenticate(self.worker)
        data = self.client.get(f'/api/v1/chat/thread/{self.owner.pk}/').data
        self.assertNotIn('language_warning', str(data))
        self.assertNotIn('fuck you', str(data))

    def test_clean_send_no_warning_and_retry_no_duplicate(self):
        key = str(uuid.uuid4())
        first = self.send(self.owner, self.worker, 'gago', key)
        second = self.send(self.owner, self.worker, 'gago', key)
        self.assertEqual(first.data, second.data)
        self.assertEqual(tbl_chat_message.objects.count(), 1)
        result = self.send(self.owner, self.worker)
        self.assertIsNone(result.data['language_warning'])

    @patch('chat.views.cloudinary.uploader.upload', return_value={'public_id': 'test_image', 'width': 10, 'height': 10})
    def test_image_caption_masked(self, upload):
        self.client.force_authenticate(self.owner)
        image = SimpleUploadedFile('test.png', b'\x89PNG\r\n\x1a\n' + b'0'*24, content_type='image/png')
        result = self.client.post('/api/v1/chat/send-image/', {'receiver_id': str(self.worker.pk),
            'image': image, 'message_payload': 'yawa'}, format='multipart', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(tbl_chat_message.objects.get().message_payload, 'y*wa')
        self.assertTrue(result.data['language_warning'])

    def test_local_officer_can_pause_lift_and_record_actor(self):
        result = self.action(self.desk, self.worker)
        self.assertEqual(result.status_code, 200, result.data)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.suspended_by_id, self.desk.pk)
        self.assertIsNotNone(self.worker.chat_suspended_until)
        self.assertEqual(self.action(self.desk, self.worker, 'resume_chat').status_code, 200)
        self.worker.refresh_from_db()
        self.assertIsNone(self.worker.chat_suspended_until)

    def test_foreign_officer_cannot_read_or_change_state(self):
        self.assertEqual(self.action(self.other_desk, self.owner).status_code, 403)
        self.assertEqual(self.client.get(f'/api/v1/chat/safety/users/{self.owner.pk}/').status_code, 403)
        self.owner.refresh_from_db()
        self.assertIsNone(self.owner.chat_suspended_until)

    def test_missing_or_conflicting_geography_cannot_authorize(self):
        for field, value in [('city', 'Other city'), ('province', 'Other province'), ('city', '')]:
            original = getattr(self.owner, field)
            setattr(self.owner, field, value); self.owner.save()
            self.assertEqual(self.action(self.desk, self.owner).status_code, 403)
            setattr(self.owner, field, original); self.owner.save()

    def test_normalized_local_geography(self):
        self.owner.barangay = 'Brgy. PAGATPAT'
        self.owner.city = 'Cagayan De Oro City'
        self.owner.save()
        self.assertEqual(self.action(self.desk, self.owner).status_code, 200)

    def test_no_self_action_no_resident_authority_no_officer_action_on_staff(self):
        for actor, target in [(self.admin, self.admin), (self.owner, self.worker),
                              (self.desk, self.admin), (self.desk, self.other_desk)]:
            self.assertEqual(self.action(actor, target).status_code, 403)
        staff = self.person('Homeowner', is_staff=True)
        self.assertEqual(self.action(self.desk, staff).status_code, 403)

    def test_superadmin_global_and_staff_authority(self):
        for target in [self.worker, self.other_desk]:
            self.assertEqual(self.action(self.admin, target, 'suspend_account').status_code, 200)
            target.refresh_from_db()
            self.assertTrue(target.is_account_suspended)
            self.assertEqual(self.action(self.admin, target, 'restore_account').status_code, 200)

    def test_only_manual_action_and_booking_penalties_untouched(self):
        self.worker.cancellation_strikes = 2; self.worker.is_restricted = True; self.worker.save()
        for _ in range(4):
            self.assertEqual(self.send(self.worker, self.owner, 'gago').status_code, 201)
        self.worker.refresh_from_db()
        self.assertIsNone(self.worker.chat_suspended_until)
        self.action(self.desk, self.worker)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.cancellation_strikes, 2)
        self.assertTrue(self.worker.is_restricted)

    def test_pause_blocks_resident_sends_but_both_official_channels_work(self):
        self.action(self.desk, self.worker)
        self.worker.refresh_from_db()
        self.assertEqual(self.send(self.worker, self.owner).status_code, 403)
        for official in [self.desk, self.admin]:
            self.assertEqual(self.send(self.worker, official).status_code, 201)
        self.assertEqual(self.send(self.worker, self.other_desk).status_code, 403)

    @patch('chat.views.cloudinary.uploader.upload')
    def test_image_rejected_before_upload_when_paused(self, upload):
        self.action(self.desk, self.worker)
        self.worker.refresh_from_db()
        self.client.force_authenticate(self.worker)
        result = self.client.post('/api/v1/chat/send-image/', {'receiver_id': str(self.owner.pk)},
            format='multipart', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(result.status_code, 403)
        upload.assert_not_called()

    def test_expiry_auto_resumes_and_status_has_no_case_reference(self):
        self.worker.chat_suspended_until = timezone.now() - timedelta(seconds=1); self.worker.save()
        self.assertEqual(self.send(self.worker, self.owner).status_code, 201)
        data = self.client.get('/api/v1/chat/safety/status/').data
        self.assertIsNone(data['restricted_until'])
        self.assertNotIn('case_id', data)

    def test_invalid_expiry_and_unknown_actions(self):
        for until in [None, 'invalid', (timezone.now()-timedelta(seconds=1)).isoformat(),
                      (timezone.now()+timedelta(days=31)).isoformat()]:
            self.assertEqual(self.action(self.desk, self.worker, until=until).status_code, 400)
        self.assertEqual(self.action(self.desk, self.worker, 'ban').status_code, 400)
        self.assertEqual(self.action(self.desk, self.worker, 'resume_chat', until='2028-01-01').status_code, 400)

    def test_account_suspension_denies_existing_jwt_login_refresh_and_recipient_sends(self):
        token = RefreshToken.for_user(self.owner)
        self.action(self.admin, self.owner, 'suspend_account')
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
        self.assertEqual(self.client.get('/api/v1/chat/inbox/').status_code, 403)
        self.client.credentials()
        response = self.client.post('/api/v1/accounts/token/refresh/', {'refresh': str(token)}, format='json')
        self.assertEqual(response.status_code, 403, response.data)
        self.owner.refresh_from_db()
        with self.assertRaises(ChatSafetyError):
            assert_messaging_allowed(self.owner, self.admin)
        self.assertEqual(self.send(self.worker, self.owner).status_code, 403)

    def test_restoring_account_does_not_lift_independent_chat_pause(self):
        self.action(self.admin, self.worker)
        self.action(self.admin, self.worker, 'suspend_account')
        self.action(self.admin, self.worker, 'restore_account')
        self.worker.refresh_from_db()
        self.assertFalse(self.worker.is_account_suspended)
        self.assertIsNotNone(self.worker.chat_suspended_until)

    def test_superseded_report_and_appeal_endpoints_removed(self):
        self.client.force_authenticate(self.owner)
        for path in ['report/', 'review/', 'cases/', f'cases/{uuid.uuid4()}/appeal/']:
            response = self.client.post('/api/v1/chat/safety/' + path, {}, format='json')
            self.assertEqual(response.status_code, 404)


    @patch('chat.views.cloudinary.uploader.destroy')
    @patch('chat.views.cloudinary.uploader.upload')
    def test_pause_during_image_upload_cleans_asset_and_does_not_send(self, upload, destroy):
        from .moderation import set_suspension
        def uploaded(*args, **kwargs):
            set_suspension(self.desk, self.owner.pk, 'pause_chat', timezone.now()+timedelta(hours=1))
            return {'public_id': 'uploaded-before-pause', 'width': 10, 'height': 10}
        upload.side_effect = uploaded
        self.client.force_authenticate(self.owner)
        image = SimpleUploadedFile('test.png', b'\x89PNG\r\n\x1a\n' + b'0'*24, content_type='image/png')
        result = self.client.post('/api/v1/chat/send-image/', {'receiver_id': str(self.worker.pk), 'image': image},
            format='multipart', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(result.status_code, 403)
        self.assertFalse(tbl_chat_message.objects.exists())
        destroy.assert_called_once_with('uploaded-before-pause', type='authenticated')

    def test_suspended_mobile_and_portal_logins_are_rejected(self):
        for account, path, body in [(self.owner, '/api/v1/accounts/login/', {'email': self.owner.email}),
                                    (self.desk, '/api/v1/accounts/admin/login/', {'email': self.desk.email})]:
            self.action(self.admin, account, 'suspend_account')
            self.client.force_authenticate(None)
            result = self.client.post(path, {**body, 'password': 'TestPassword123!'}, format='json')
            self.assertEqual(result.status_code, 403, result.data)


    def access_roster(self, actor, **query):
        self.client.force_authenticate(actor)
        return self.client.get('/api/v1/accounts/admin/users/', {'access_management': '1', **query})

    def test_access_roster_only_includes_residents_and_real_suspension_state(self):
        self.action(self.desk, self.worker)
        self.action(self.admin, self.owner, 'suspend_account')
        response = self.access_roster(self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        users = {row['id']: row for row in response.data}
        self.assertEqual(set(users), {str(self.owner.pk), str(self.worker.pk)})
        self.assertTrue(users[str(self.owner.pk)]['isAccountSuspended'])
        self.assertTrue(users[str(self.worker.pk)]['chatSuspendedUntil'])
        self.assertTrue(all(row['canManageSuspension'] for row in users.values()))
        self.assertTrue(all(row['role'] in ['HOMEOWNER', 'KASAMBAHAY'] for row in users.values()))

    def test_access_roster_local_scope_ignores_forged_barangay_and_role(self):
        foreign = self.person('Kasambahay', barangay='Carmen')
        conflict = self.person('Homeowner', city='Other City')
        incomplete = self.person('Homeowner', province='')
        staff = self.person('Homeowner', is_staff=True)
        response = self.access_roster(self.desk, barangay='Carmen', role='SUPERADMIN')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['id'] for row in response.data}, {str(self.owner.pk), str(self.worker.pk)})
        for target in [foreign, conflict, incomplete, staff]:
            self.assertNotIn(str(target.pk), {row['id'] for row in response.data})

    def test_access_roster_retains_deactivated_and_suspended_local_residents(self):
        self.owner.is_active = False; self.owner.save(update_fields=['is_active'])
        self.action(self.desk, self.worker, 'suspend_account')
        response = self.access_roster(self.desk)
        rows = {row['id']: row for row in response.data}
        self.assertFalse(rows[str(self.owner.pk)]['isAccountActive'])
        self.assertTrue(rows[str(self.worker.pk)]['isAccountSuspended'])

    def test_access_roster_denies_residents_and_uses_registered_barangay_for_filters(self):
        self.assertEqual(self.access_roster(self.owner).status_code, 403)
        foreign = self.person('Homeowner', barangay='Carmen', street='Near Pagatpat')
        unassigned = self.person('Homeowner', barangay='', street='Pagatpat')
        response = self.access_roster(self.admin, barangay='Brgy. PAGATPAT')
        self.assertEqual({row['id'] for row in response.data}, {str(self.owner.pk), str(self.worker.pk)})
        self.assertNotIn(str(foreign.pk), {row['id'] for row in response.data})
        response = self.access_roster(self.admin, barangay='UNASSIGNED')
        self.assertEqual([row['id'] for row in response.data], [str(unassigned.pk)])
        self.assertEqual(response.data[0]['barangay'], 'Unassigned')
