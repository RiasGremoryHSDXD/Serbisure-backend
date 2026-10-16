"""Support discovery and chat authorization, always based on saved account profiles."""
import re

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

RESIDENT_ROLES = ('Homeowner', 'Kasambahay')


def is_superadmin(user):
    return user.account_type != 'Barangay' and (user.account_type == 'Admin' or user.is_superuser)


def location_key(value, barangay=False):
    value = (value or '').strip()
    if barangay:
        value = re.sub(r'^(brgy\.?|barangay)\s+', '', value, flags=re.I)
    return ' '.join(value.split()).casefold()


def jurisdiction_parts(profile):
    return (location_key(profile.barangay, barangay=True),
        re.sub(r'^city of\s+|\s+city$', '', location_key(profile.city)).strip(),
        location_key(profile.province))


def jurisdiction(profile):
    key = jurisdiction_parts(profile)
    return key if all(key) else None


def same_barangay(left, right):
    name = location_key(left.barangay, barangay=True)
    if not name or name != location_key(right.barangay, barangay=True):
        return False
    # A matching barangay name must not override conflicting city/province information.
    for field in ('city', 'province'):
        first, second = location_key(getattr(left, field)), location_key(getattr(right, field))
        if field == 'city':
            first = re.sub(r'^city of\s+|\s+city$', '', first)
            second = re.sub(r'^city of\s+|\s+city$', '', second)
        if first and second and first != second:
            return False
    return True


def can_chat(user, partner):
    if not user.is_active or not partner.is_active or user.pk == partner.pk:
        return False
    if user.account_type == 'Barangay' and partner.account_type == 'Barangay':
        return False
    if is_superadmin(user) or is_superadmin(partner):
        return True
    if user.account_type == 'Barangay':
        return partner.account_type in RESIDENT_ROLES and same_barangay(user, partner)
    if partner.account_type == 'Barangay':
        return user.account_type in RESIDENT_ROLES and same_barangay(user, partner)
    return user.account_type in RESIDENT_ROLES and partner.account_type in RESIDENT_ROLES


def assert_chat_access(user, partner):
    if not can_chat(user, partner):
        raise PermissionDenied('You can only contact your own barangay desk or SerbiSure Support.')


def assert_message_access(user, message):
    if user.pk not in (message.sender_id_id, message.receiver_id_id):
        raise PermissionDenied('You are not a participant of this conversation.')
    partner = message.receiver_id if message.sender_id_id == user.pk else message.sender_id
    assert_chat_access(user, partner)


def support_contacts(user):
    if user.account_type not in RESIDENT_ROLES:
        raise PermissionDenied('Support contacts are available to homeowners and kasambahays.')
    accounts = get_user_model().objects.filter(is_active=True, is_account_suspended=False).filter(
        Q(account_type__in=['Admin', 'Barangay']) | Q(is_superuser=True)
    ).order_by('date_joined', 'pk')
    admins, desks = [], []
    for account in accounts:
        if is_superadmin(account):
            admins.append(account)
        elif account.account_type == 'Barangay' and same_barangay(user, account):
            desks.append(account)
    name = (user.barangay or '').strip()
    return {
        'superadmins': admins,
        'barangay': {
            'name': name, 'available': bool(desks), 'contacts': desks,
            'message': '' if desks else (
                'Your barangay desk is not available yet. Contact SerbiSure Support for help.' if name else
                'Add your barangay to your profile to find your local desk. You can contact SerbiSure Support now.'
            ),
        },
    }
