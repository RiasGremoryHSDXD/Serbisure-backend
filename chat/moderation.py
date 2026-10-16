"""Manual account controls and outgoing sanitization. No automated penalties."""
import re
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied
from realtime.events import publish
from .moderation_rules import mask_text
from .services import RESIDENT_ROLES, can_chat, is_superadmin, location_key

LANGUAGE_NOTICE = ('Inappropriate or threatening language was detected in your message. '
    'Please communicate respectfully. Harassment and threats can be reported to your Barangay '
    'or SerbiSure Support and may lead to temporary messaging suspension.')


class ChatSafetyError(APIException):
    status_code = 403

    def __init__(self, code, detail, **metadata):
        super().__init__({'code': code, 'detail': detail, **metadata})


def restriction_until(user):
    until = user.chat_suspended_until
    return until if until and until > timezone.now() else None


def assert_messaging_allowed(user, partner=None):
    if user.is_account_suspended:
        raise ChatSafetyError('account_suspended', 'Your account is suspended. Contact SerbiSure Support for assistance.')
    if partner and partner.is_account_suspended:
        raise ChatSafetyError('recipient_suspended', 'This account is currently unavailable.')
    until = restriction_until(user)
    official = partner and (is_superadmin(partner) or partner.account_type == 'Barangay') and can_chat(user, partner)
    if until and not official:
        raise ChatSafetyError('messaging_restricted',
            'Messaging is temporarily paused. You can still contact your Barangay desk or SerbiSure Support.',
            expires_at=until.isoformat())


def inspect_outgoing(user, partner, text, request_key='', channel='message'):
    assert_messaging_allowed(user, partner)
    return mask_text(text or '')


def jurisdiction(profile):
    barangay = location_key(profile.barangay, barangay=True)
    city = re.sub(r'^city of\s+|\s+city$', '', location_key(profile.city)).strip()
    province = location_key(profile.province)
    return (barangay, city, province) if all((barangay, city, province)) else None


def may_manage(actor, target):
    if not actor.is_active or actor.is_account_suspended or actor.pk == target.pk:
        return False
    if is_superadmin(actor):
        return True
    key = jurisdiction(actor)
    return bool(actor.account_type == 'Barangay' and target.account_type in RESIDENT_ROLES
        and not target.is_staff and not target.is_superuser and key and key == jurisdiction(target))


@transaction.atomic
def set_suspension(actor, target_id, action, until=None):
    users = {u.pk: u for u in get_user_model().objects.select_for_update().filter(
        pk__in=[actor.pk, target_id]).order_by('pk')}
    actor, target = users.get(actor.pk), users.get(target_id)
    if not actor or not target or not may_manage(actor, target):
        raise PermissionDenied('You may only manage eligible accounts within your jurisdiction.')
    if action == 'pause_chat':
        target.chat_suspended_until = until
    elif action == 'resume_chat':
        target.chat_suspended_until = None
    elif action == 'suspend_account':
        target.is_account_suspended = True
    elif action == 'restore_account':
        target.is_account_suspended = False
    target.suspended_by = actor
    target.save(update_fields=['chat_suspended_until', 'is_account_suspended', 'suspended_by'])
    publish([target.pk, actor.pk], {'type': 'moderation.changed'})
    return target
