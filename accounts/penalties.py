"""Calendar-month booking penalties. Messaging and account suspension are separate."""
from datetime import datetime
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

PH_TIME = ZoneInfo('Asia/Manila')


def current_penalty_month():
    return timezone.now().astimezone(PH_TIME).date().replace(day=1)


def next_penalty_month(at=None):
    day = (at or timezone.now()).astimezone(PH_TIME)
    return datetime(day.year + (day.month == 12), day.month % 12 + 1, 1, tzinfo=PH_TIME)


def refresh_monthly_penalties(user):
    month = current_penalty_month()
    if user.penalty_month >= month:
        return user
    with transaction.atomic():
        saved = get_user_model().objects.select_for_update().get(pk=user.pk)
        if saved.penalty_month < month:
            saved.penalty_points = 0
            saved.is_restricted = False
            saved.penalty_month = month
            saved.save(update_fields=['penalty_points', 'penalty_month', 'is_restricted'])
        user.penalty_points = saved.penalty_points
        user.penalty_month = saved.penalty_month
        user.is_restricted = saved.is_restricted
    return user


def assert_booking_unrestricted(user):
    refresh_monthly_penalties(user)
    if user.is_restricted or user.penalty_points >= 3:
        raise PermissionDenied({'code': 'booking_restricted',
            'detail': 'Booking and posting are restricted until next month.' if user.penalty_points >= 3
                      else 'Booking and posting are restricted. Contact Support.'})


def penalty_status(user):
    refresh_monthly_penalties(user)
    return {'penalty_points': user.penalty_points, 'is_restricted': user.is_restricted,
            'penalty_month': user.penalty_month.isoformat(), 'resets_at': next_penalty_month().isoformat()}
