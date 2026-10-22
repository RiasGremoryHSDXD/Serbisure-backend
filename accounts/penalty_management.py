"""Scoped reads and atomic, audited manual adjustments of existing monthly points."""
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from booking.models import tbl_booking
from chat.services import RESIDENT_ROLES, is_superadmin, jurisdiction, jurisdiction_parts, location_key
from realtime.events import publish
from .penalties import PH_TIME, current_penalty_month, refresh_monthly_penalties
from .penalty_models import PenaltyAdjustment


def assert_official(actor):
    if not actor.is_active or actor.is_account_suspended or not (
        is_superadmin(actor) or (actor.account_type == 'Barangay' and jurisdiction(actor))
    ):
        raise PermissionDenied('Only authorized administrators can manage penalty points.')


def resident_queryset(actor, filters=None):
    assert_official(actor)
    filters = filters or {}
    users = get_user_model().objects.filter(account_type__in=RESIDENT_ROLES, is_staff=False, is_superuser=False)
    # Reuse the saved-profile policy, including normalized city and province. One
    # lightweight location query avoids trusting a client-supplied barangay.
    if actor.account_type == 'Barangay':
        key = jurisdiction(actor)
        ids = [user.pk for user in users.only('id', 'barangay', 'city', 'province') if jurisdiction(user) == key]
        users = users.filter(pk__in=ids)
    elif filters.get('barangay') and filters['barangay'] not in ('All Barangays', 'ALL'):
        key = location_key(filters['barangay'], barangay=True)
        covered = {location_key(value, barangay=True) for value in get_user_model().objects.filter(
            account_type='Barangay', is_active=True).values_list('barangay', flat=True)} if key == 'unassigned' else set()
        ids = [user.pk for user in users.only('id', 'barangay') if (
            location_key(user.barangay, barangay=True) not in covered if key == 'unassigned'
            else location_key(user.barangay, barangay=True) == key)]
        users = users.filter(pk__in=ids)
    if filters.get('role'):
        users = users.filter(account_type=filters['role'])
    if filters.get('points'):
        # Match the effective score shown in the portal, including last month's
        # points appearing as zero without writing a reset during a list request.
        month = current_penalty_month()
        if filters['points'] == '0':
            users = users.filter(Q(penalty_month__lt=month) | Q(penalty_points=0))
        else:
            users = users.filter(penalty_month__gte=month)
            if filters['points'] == 'with_penalties':
                users = users.filter(penalty_points__gt=0)
            else:
                users = users.filter(penalty_points=int(filters['points']))
    if filters.get('search'):
        term = filters['search']
        users = users.annotate(full_name=Concat('first_name', Value(' '), 'last_name')).filter(
            Q(full_name__icontains=term) | Q(username__icontains=term) | Q(barangay__icontains=term))
    return users.order_by('first_name', 'last_name', 'id')


def effective_points(user):
    return user.penalty_points if user.penalty_month >= current_penalty_month() else 0


def cancellations_for(user):
    month = current_penalty_month()
    since = datetime(month.year, month.month, 1, tzinfo=PH_TIME)
    return tbl_booking.objects.filter(cancelled_by=user, booking_status='Cancelled', cancelled_at__gte=since).order_by('-cancelled_at', '-pk')


def adjustment_history(actor, filters=None):
    assert_official(actor)
    filters = filters or {}
    records = PenaltyAdjustment.objects.all()
    if actor.account_type == 'Barangay':
        key = jurisdiction(actor)
        records = records.filter(barangay_key=key[0], city_key=key[1], province_key=key[2])
    elif filters.get('barangay') and filters['barangay'] not in ('All Barangays', 'ALL'):
        key = location_key(filters['barangay'], barangay=True)
        if key == 'unassigned':
            covered = [location_key(value, barangay=True) for value in get_user_model().objects.filter(
                account_type='Barangay', is_active=True).values_list('barangay', flat=True)]
            records = records.exclude(barangay_key__in=covered)
        else:
            records = records.filter(barangay_key=key)
    if filters.get('user_id'):
        records = records.filter(user_id_snapshot=filters['user_id'])
    if filters.get('role'):
        records = records.filter(user_role=filters['role'])
    if filters.get('search'):
        term = filters['search']
        records = records.filter(Q(user_name__icontains=term) | Q(admin_name__icontains=term)
            | Q(user_barangay__icontains=term) | Q(incident_reference__icontains=term))
    return records


def conflict(message='Points changed. Refresh before adjusting.'):
    error = APIException({'detail': message})
    error.status_code = 409
    raise error


@transaction.atomic
def adjust_points(actor, user_id, data):
    people = {user.pk: user for user in get_user_model().objects.select_for_update().filter(
        pk__in=[actor.pk, user_id]).order_by('pk')}
    actor = people.get(actor.pk)
    if actor is None:
        raise PermissionDenied('Your administrator account is unavailable.')
    # Recheck scope against the locked profiles, never the supplied role/filter.
    get_object_or_404(resident_queryset(actor), pk=user_id)
    user = people[user_id]
    existing = PenaltyAdjustment.objects.filter(request_id=data['request_id']).first()
    if existing:
        same = (existing.admin_id_snapshot == actor.pk and existing.user_id_snapshot == user.pk
            and existing.points_delta == data['points_delta'] and existing.reason == data['reason']
            and existing.penalty_month == data['expected_month'] and existing.points_before == data['expected_points']
            and existing.report_verified == data['report_verified'] and existing.incident_reference == data['incident_reference']
            and existing.booking_id_snapshot == data.get('booking_id'))
        if not same:
            conflict('This request was already used. Refresh and try again.')
        return user, existing, False
    month = current_penalty_month()
    refresh_monthly_penalties(user)
    if data['expected_month'] != month or user.penalty_month != month or data['expected_points'] != user.penalty_points:
        conflict()
    points = user.penalty_points + data['points_delta']
    if not 0 <= points <= 3:
        raise ValidationError({'detail': 'The new score must be between 0 and 3 points.'})
    booking_id = data.get('booking_id')
    if booking_id and not cancellations_for(user).filter(pk=booking_id).exists():
        raise ValidationError({'detail': 'Choose one of this user’s cancellations from this month.'})
    before = user.penalty_points
    user.penalty_points = points
    user.is_restricted = points >= 3
    user.save(update_fields=['penalty_points', 'is_restricted'])
    key = jurisdiction_parts(user)
    try:
        record = PenaltyAdjustment.objects.create(
            request_id=data['request_id'], user_id_snapshot=user.pk,
            user_name=user.get_full_name().strip() or user.username, user_role=user.account_type,
            user_barangay=user.barangay or '', barangay_key=key[0], city_key=key[1], province_key=key[2],
            admin_id_snapshot=actor.pk, admin_name=actor.get_full_name().strip() or actor.username,
            admin_role=actor.account_type, points_delta=data['points_delta'], points_before=before,
            points_after=points, penalty_month=month, reason=data['reason'],
            report_verified=data['report_verified'], incident_reference=data['incident_reference'],
            booking_id_snapshot=booking_id)
    except IntegrityError:
        conflict('This request was already used. Refresh and try again.')
    publish([user.pk, actor.pk], {'type': 'booking.changed', 'booking_id': str(booking_id) if booking_id else None})
    return user, record, True
