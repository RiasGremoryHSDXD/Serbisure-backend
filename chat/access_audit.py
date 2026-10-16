"""Append-only account access history and jurisdiction-scoped reads."""
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from .models import AccountAccessAudit
from .services import RESIDENT_ROLES, is_superadmin, jurisdiction, jurisdiction_parts, location_key


def record_access_change(actor, target, action, before, after):
    """Called inside the suspension transaction; failure must roll back the action."""
    key = jurisdiction_parts(target)
    return AccountAccessAudit.objects.create(
        actor_id_snapshot=actor.pk,
        actor_name=actor.get_full_name().strip() or actor.username or actor.email,
        actor_role=actor.account_type,
        actor_barangay=actor.barangay or '',
        target_id_snapshot=target.pk,
        target_name=target.get_full_name().strip() or target.username or target.email,
        target_role=target.account_type,
        target_barangay=target.barangay or '',
        target_is_staff=target.is_staff or target.is_superuser,
        barangay_key=key[0], city_key=key[1], province_key=key[2],
        action=action, previous_state=before, new_state=after,
    )


def access_history(actor, filters):
    if not actor.is_active or actor.is_account_suspended:
        raise PermissionDenied('Account access history is unavailable.')
    records = AccountAccessAudit.objects.all()
    if not is_superadmin(actor):
        key = jurisdiction(actor)
        if actor.account_type != 'Barangay' or not key:
            raise PermissionDenied('Only authorized officials can read account access history.')
        records = records.filter(target_role__in=RESIDENT_ROLES, target_is_staff=False,
            barangay_key=key[0], city_key=key[1], province_key=key[2])
    if filters.get('barangay') and is_superadmin(actor):
        barangay = location_key(filters['barangay'], barangay=True)
        records = records.filter(barangay_key='' if barangay == 'unassigned' else barangay)
    if filters.get('action'):
        records = records.filter(action=filters['action'])
    if filters.get('role'):
        records = records.filter(target_role=filters['role'])
    if filters.get('user_id'):
        records = records.filter(target_id_snapshot=filters['user_id'])
    if filters.get('search'):
        term = filters['search']
        records = records.filter(Q(target_name__icontains=term) | Q(actor_name__icontains=term)
            | Q(target_barangay__icontains=term))
    return records
