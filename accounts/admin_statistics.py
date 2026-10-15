"""Database-only workforce and barangay coverage snapshots for the portal."""
import re
from collections import defaultdict
from rest_framework.exceptions import PermissionDenied
from .models import tbl_user_profile


def barangay_name(value):
    return re.sub(r'^(brgy\.?|barangay)\s+', '', (value or '').strip(), flags=re.I).strip()


def scope_for(request):
    if request.user.account_type == 'Barangay':
        if not barangay_name(request.user.barangay):
            raise PermissionDenied('Your LGU account has no assigned barangay.')
        return request.user.barangay
    return request.query_params.get('barangay') or 'All Barangays'


def resident_snapshot(scope='All Barangays', restrict_directory=False):
    from booking.models import tbl_booking_assignment, tbl_booking
    users = list(tbl_user_profile.objects.filter(account_type__in=['Kasambahay', 'Homeowner'], is_active=True).prefetch_related('documents'))
    active = {}
    for value in tbl_user_profile.objects.filter(account_type='Barangay', is_active=True).values_list('barangay', flat=True):
        name = barangay_name(value)
        if name:
            active.setdefault(name.casefold(), name)
    groups, names = defaultdict(list), dict(active)
    for user in users:
        name = barangay_name(user.barangay)
        key = name.casefold()
        groups[key].append(user)
        if name and key != 'unassigned':
            names.setdefault(key, name)
    key = barangay_name(scope).casefold()
    if key in ['all', 'all barangays']:
        scoped = users
    elif key in ['unassigned', 'no lgu coverage', 'no_lgu']:
        # An empty LGU list means every resident lacks coverage, not an empty queryset.
        scoped = [user for user in users if barangay_name(user.barangay).casefold() not in active]
    else:
        scoped = groups.get(key, [])
    active_bookings = tbl_booking.objects.filter(booking_status__in=['Accepted', 'InProgress'])
    hired_ids = set(active_bookings.filter(poster_id__account_type='Kasambahay').values_list('poster_id', flat=True))
    hired_ids.update(tbl_booking_assignment.objects.filter(booking_id__in=active_bookings, accepter_id__account_type='Kasambahay').values_list('accepter_id', flat=True))
    def stats(residents):
        workers = [user for user in residents if user.account_type == 'Kasambahay']
        employed = sum(user.is_on_job or user.pk in hired_ids for user in workers)
        counts = {'pending': 0, 'verified': 0, 'rejected': 0, 'noDocuments': 0}
        for user in residents:
            # Count citizens once, using the same bilateral document rules as mobile.
            counts[{'Pending': 'pending', 'Verified': 'verified', 'Rejected': 'rejected'}.get(user.verification_status, 'noDocuments')] += 1
        return {'totalRegistered': len(residents), 'totalWorkers': len(workers), 'employed': employed,
                'available': len(workers) - employed,
                'employmentRatio': round(employed / len(workers) * 100) if workers else 0, **counts}
    totals = stats(scoped)
    rows = [{'name': name, 'status': 'ACTIVE' if name_key in active else 'INACTIVE', **stats(groups[name_key])}
            for name_key, name in sorted(names.items(), key=lambda entry: entry[1].casefold())
            if not restrict_directory or name_key == key]
    pending_documents = sum(doc.verification_status == 'Pending' for user in scoped for doc in user.documents.all())
    return {'metrics': {'totalWorkers': totals['totalWorkers'], 'totalEmployed': totals['employed'],
                        'totalAvailable': totals['available'], 'employmentRatio': totals['employmentRatio'],
                        'totalHomeowners': sum(user.account_type == 'Homeowner' for user in scoped),
                        'pendingVerifications': pending_documents}, 'barangays': rows}
