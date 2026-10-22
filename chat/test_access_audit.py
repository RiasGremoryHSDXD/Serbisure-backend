from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import AccountAccessAudit
from .moderation import set_suspension

User = get_user_model()
HISTORY = '/api/v1/chat/safety/history/'


class AccountAccessAuditTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.publish = patch('chat.moderation.publish').start()
        self.addCleanup(patch.stopall)
        self.sequence = 0
        self.admin = self.person('Admin', first_name='City', last_name='Admin')
        self.desk = self.person('Barangay', first_name='Pagatpat', last_name='Desk')
        self.other_desk = self.person('Barangay', barangay='Carmen')
        self.resident = self.person('Homeowner', first_name='Ana', last_name='Cruz')
        self.foreign = self.person('Kasambahay', barangay='Carmen')

    def person(self, role, **fields):
        self.sequence += 1
        data = dict(barangay='Pagatpat', city='City of Cagayan de Oro', province='Misamis Oriental')
        data.update(fields)
        return User.objects.create_user(username=f'audit{self.sequence}', email=f'audit{self.sequence}@example.test',
            password='Password123!', account_type=role, contact_number=f'+63917777{self.sequence:04}', **data)

    def change(self, actor=None, target=None, action='pause_chat'):
        until = timezone.now() + timedelta(hours=24) if action == 'pause_chat' else None
        return set_suspension(actor or self.desk, (target or self.resident).pk, action, until)

    def history(self, actor=None, **params):
        self.client.force_authenticate(actor or self.admin)
        return self.client.get(HISTORY, params)

    def test_all_manual_transitions_record_actor_target_and_independent_before_after(self):
        for action in ('pause_chat', 'suspend_account', 'restore_account', 'resume_chat'):
            self.change(action=action)
        logs = list(AccountAccessAudit.objects.order_by('created_at', 'log_id'))
        self.assertEqual([log.action for log in logs], ['pause_chat', 'suspend_account', 'restore_account', 'resume_chat'])
        self.assertEqual(logs[0].previous_state, {'is_account_suspended': False, 'chat_suspended_until': None})
        self.assertTrue(logs[0].new_state['chat_suspended_until'])
        self.assertTrue(logs[1].new_state['is_account_suspended'])
        self.assertEqual(logs[2].new_state['chat_suspended_until'], logs[0].new_state['chat_suspended_until'])
        self.assertFalse(logs[2].new_state['is_account_suspended'])
        self.assertIsNone(logs[3].new_state['chat_suspended_until'])
        self.assertTrue(all(log.actor_id_snapshot == self.desk.pk and log.actor_name == 'Pagatpat Desk'
            and log.target_id_snapshot == self.resident.pk and log.target_name == 'Ana Cruz' for log in logs))

    def test_post_records_but_read_invalid_denied_and_unchanged_actions_do_not(self):
        self.client.force_authenticate(self.desk)
        path = f'/api/v1/chat/safety/users/{self.resident.pk}/'
        self.assertEqual(self.client.post(path, {'action': 'suspend_account'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(path, {'action': 'suspend_account'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(path, {'action': 'unknown'}, format='json').status_code, 400)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.client.force_authenticate(self.other_desk)
        self.assertEqual(self.client.post(path, {'action': 'restore_account'}, format='json').status_code, 403)
        self.assertEqual(AccountAccessAudit.objects.count(), 1)

    def test_audit_failure_rolls_back_access_change_and_does_not_publish(self):
        with patch('chat.moderation.record_access_change', side_effect=DatabaseError('unavailable')):
            with self.assertRaises(DatabaseError):
                self.change()
        self.resident.refresh_from_db()
        self.assertIsNone(self.resident.chat_suspended_until)
        self.assertIsNone(self.resident.suspended_by)
        self.assertEqual(AccountAccessAudit.objects.count(), 0)
        self.publish.assert_not_called()

    def test_superadmin_sees_all_but_barangay_only_sees_snapshot_jurisdiction(self):
        self.change()
        self.change(actor=self.admin, target=self.foreign)
        self.change(actor=self.admin, target=self.other_desk)
        self.assertEqual(self.history().data['count'], 3)
        local = self.history(self.desk, barangay='Carmen', role='Homeowner')
        self.assertEqual(local.status_code, 200)
        self.assertEqual(local['Cache-Control'], 'private, no-store')
        self.assertEqual([row['target_id_snapshot'] for row in local.data['results']], [str(self.resident.pk)])
        self.assertEqual(self.history(self.other_desk).status_code, 200)
        self.assertEqual(self.history(self.other_desk).data['count'], 1)

    def test_missing_conflicting_or_staff_scope_never_leaks_records(self):
        staff = self.person('Homeowner', is_staff=True)
        conflict = self.person('Homeowner', city='Other City')
        missing = self.person('Homeowner', province='')
        for person in (staff, conflict, missing):
            self.change(actor=self.admin, target=person)
        self.assertEqual(self.history(self.desk).data['count'], 0)
        self.desk.city = ''; self.desk.save(update_fields=['city'])
        self.assertEqual(self.history(self.desk).status_code, 403)

    def test_identity_and_jurisdiction_snapshots_survive_edits_and_account_deletion(self):
        self.change()
        log = AccountAccessAudit.objects.get()
        self.resident.first_name = 'Renamed'; self.resident.barangay = 'Carmen'; self.resident.save()
        self.desk.first_name = 'Renamed'; self.desk.save()
        self.assertEqual(self.history(self.desk).data['count'], 1)
        self.assertEqual(self.history(self.other_desk).data['count'], 0)
        self.resident.delete(); self.desk.delete()
        log.refresh_from_db()
        self.assertEqual(log.target_name, 'Ana Cruz')
        self.assertEqual(log.actor_name, 'Pagatpat Desk')
        self.assertEqual(log.target_barangay, 'Pagatpat')
        self.assertEqual(self.history().data['count'], 1)

    def test_normalized_geography_and_superadmin_barangay_filter(self):
        self.resident.barangay = 'Brgy. PAGATPAT'; self.resident.city = 'Cagayan de Oro City'; self.resident.save()
        self.change()
        self.change(actor=self.admin, target=self.foreign)
        self.assertEqual(self.history(self.desk).data['count'], 1)
        self.assertEqual(self.history(barangay='Barangay Pagatpat').data['count'], 1)
        self.assertEqual(self.history(barangay='Carmen').data['count'], 1)

    def test_read_only_api_authentication_authorization_and_validation(self):
        self.assertEqual(self.client.get(HISTORY).status_code, 401)
        self.assertEqual(self.history(self.resident).status_code, 403)
        for params in ({'action': 'ban'}, {'role': 'Admin'}, {'user_id': 'invalid'}, {'search': 'x' * 201}):
            self.assertEqual(self.history(**params).status_code, 400)
        self.client.force_authenticate(self.admin)
        for method in ('post', 'put', 'patch', 'delete'):
            self.assertEqual(getattr(self.client, method)(HISTORY, {}, format='json').status_code, 405)
        self.admin.is_account_suspended = True; self.admin.save(update_fields=['is_account_suspended'])
        self.assertEqual(self.history().status_code, 403)

    def test_search_action_target_filters_and_bounded_newest_first_pagination(self):
        for index in range(12):
            self.change(action='suspend_account' if index % 2 == 0 else 'restore_account')
        first = self.history()
        second = self.history(page=2)
        third = self.history(page=3)
        self.assertEqual(first.data['count'], 12)
        self.assertEqual(len(first.data['results']), 5)
        self.assertEqual(len(second.data['results']), 5)
        self.assertEqual(len(third.data['results']), 2)
        self.assertFalse({row['log_id'] for row in first.data['results']} & {row['log_id'] for row in second.data['results']})
        self.assertEqual(first.data['results'][0]['action'], 'restore_account')
        self.assertEqual(self.history(action='restore_account', search='ana').data['count'], 6)
        self.assertEqual(self.history(user_id=str(self.foreign.pk)).data['count'], 0)
        self.assertEqual(self.history(page=99).status_code, 404)

    def test_orm_and_database_reject_mutations_including_raw_sql(self):
        self.change()
        log = AccountAccessAudit.objects.get()
        log.actor_name = 'Forged'
        for mutate in (lambda: log.save(), lambda: log.delete(),
            lambda: AccountAccessAudit.objects.filter(pk=log.pk).update(actor_name='Forged'),
            lambda: AccountAccessAudit.objects.all().delete(),
            lambda: AccountAccessAudit.objects.bulk_update([log], ['actor_name'])):
            with self.assertRaises(ValidationError):
                mutate()
        for sql, params in (
            ('UPDATE tbl_account_access_audit SET actor_name = %s WHERE log_id = %s', ['Forged', log.pk]),
            ('DELETE FROM tbl_account_access_audit WHERE log_id = %s', [log.pk]),
        ):
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, params)
        if connection.vendor == 'postgresql':
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('TRUNCATE tbl_account_access_audit')
        log.refresh_from_db()
        self.assertEqual(log.actor_name, 'Pagatpat Desk')
        self.assertEqual(AccountAccessAudit.objects.count(), 1)
