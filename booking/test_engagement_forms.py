from datetime import datetime, timedelta
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from .models import tbl_booking
from .services import PH_TIME


class EngagementFormTests(APITestCase):
    """Both form entry points persist the same actual terms, for either account role."""
    def setUp(self):
        user = get_user_model()
        self.owner = user.objects.create_user(email='form-owner@test.com', username='form-owner', password='test', account_type='Homeowner', verification_status='Verified')
        self.worker = user.objects.create_user(email='form-worker@test.com', username='form-worker', password='test', account_type='Kasambahay', verification_status='Verified')

    def terms(self, long_term=False, start_hour=8, end_hour=12):
        start = (timezone.now().astimezone(PH_TIME) + timedelta(days=3)).replace(hour=start_hour, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=30 if long_term else 0)).replace(hour=end_hour)
        return dict(booking_type='long_term' if long_term else 'short_term', work_setup='stay_in' if long_term else 'stay_out',
            service_category=['Cleaning', 'Child_care', 'Cooking', 'Caregiver', 'Laundry'],
            start_time=start.isoformat(), end_time=end.isoformat(),
            work_days=[['M', 'T', 'W', 'Th', 'F', 'S', 'Su'][start.weekday()]],
            daily_start_time=f'{start_hour:02d}:00:00', daily_end_time=f'{end_hour:02d}:00:00',
            region='Region X - Northern Mindanao', province='Misamis Oriental', city='City of Cagayan De Oro',
            barangay='Carmen', street='12 Test Street', floor_number='2', zip_code='9000',
            rate_amount='8000' if long_term else '800', rate_period='month' if long_term else 'day')

    def send(self, sender, receiver, chat, data):
        self.client.force_authenticate(sender)
        payload = dict(data)
        if chat:
            payload['recipient_id'] = str(receiver.pk)
        return self.client.post(reverse('booking-chat-offer' if chat else 'booking-post'), payload,
            format='json', HTTP_IDEMPOTENCY_KEY=str(uuid4()))

    def test_both_roles_and_entry_points_preserve_full_location_and_long_term_schedule(self):
        for sender, receiver in ((self.owner, self.worker), (self.worker, self.owner)):
            for chat in (False, True):
                terms = self.terms(long_term=True, end_hour=17)
                response = self.send(sender, receiver, chat, terms)
                self.assertEqual(response.status_code, 201, response.data)
                saved = response.data['booking' if chat else 'data']
                row = tbl_booking.objects.get(pk=saved['booking_id'])
                self.assertEqual(row.service_category, ['All-around'])
                for field in ('region', 'province', 'city', 'barangay', 'street', 'floor_number', 'zip_code', 'work_days', 'work_setup', 'rate_period'):
                    self.assertEqual(getattr(row, field), terms[field], field)
                    self.assertEqual(saved[field], terms[field], field)
                self.assertEqual(row.start_time.isoformat(), datetime.fromisoformat(terms['start_time']).astimezone(row.start_time.tzinfo).isoformat())
                self.assertEqual(str(row.daily_start_time), '08:00:00')
                self.assertEqual(str(row.daily_end_time), '17:00:00')

    def test_all_three_short_term_shifts_preserve_selected_date_and_times(self):
        for start_hour, end_hour in ((8, 12), (12, 17), (17, 21)):
            for chat in (False, True):
                terms = self.terms(start_hour=start_hour, end_hour=end_hour)
                response = self.send(self.worker, self.owner, chat, terms)
                self.assertEqual(response.status_code, 201, response.data)
                row = tbl_booking.objects.get(pk=response.data['booking' if chat else 'data']['booking_id'])
                self.assertEqual(row.start_time.astimezone(PH_TIME).date(), datetime.fromisoformat(terms['start_time']).date())
                self.assertEqual(row.end_time.astimezone(PH_TIME).date(), row.start_time.astimezone(PH_TIME).date())
                self.assertEqual(str(row.daily_start_time), terms['daily_start_time'])
                self.assertEqual(str(row.daily_end_time), terms['daily_end_time'])
                self.assertEqual(row.work_days, terms['work_days'])

    def test_both_entry_points_reject_inconsistent_clocks_days_and_unsupported_regions(self):
        terms = self.terms(long_term=True, end_hour=17)
        other_day = next(day for day in ('M', 'T', 'W', 'Th', 'F', 'S', 'Su') if day not in terms['work_days'])
        for updates in ({'daily_start_time': '09:00:00'}, {'daily_end_time': '18:00:00'},
                        {'work_days': [other_day]}, {'work_days': terms['work_days'] * 2}, {'region': 'Unsupported Region'}):
            for chat in (False, True):
                response = self.send(self.owner, self.worker, chat, {**terms, **updates})
                self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(tbl_booking.objects.exists())
