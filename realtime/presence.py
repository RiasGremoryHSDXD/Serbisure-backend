"""Short-lived, per-connection presence shared by ASGI workers through Redis."""
import logging
import threading
import time
from functools import lru_cache
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model

from chat.services import can_chat

logger = logging.getLogger(__name__)
PRESENCE_TTL = 65
_connections = {}
_lock = threading.Lock()


def presence_group(user_id):
    return f'presence.{user_id}'


@lru_cache(maxsize=1)
def redis_client(url):
    from redis import Redis
    return Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)


def update_presence(user_id, connection_id, connected):
    """A second tab keeps the account online when the first tab disconnects."""
    now = time.time()
    try:
        if settings.REDIS_URL:
            key = f'realtime:presence:{user_id}'
            with redis_client(settings.REDIS_URL).pipeline() as pipe:
                pipe.zremrangebyscore(key, '-inf', now)
                if connected:
                    pipe.zadd(key, {connection_id: now + PRESENCE_TTL})
                else:
                    pipe.zrem(key, connection_id)
                pipe.zcard(key)
                pipe.expire(key, PRESENCE_TTL)
                return bool(pipe.execute()[2])
        with _lock:
            sessions = _connections.setdefault(str(user_id), {})
            for key, expires in list(sessions.items()):
                if expires <= now:
                    del sessions[key]
            if connected:
                sessions[connection_id] = now + PRESENCE_TTL
            else:
                sessions.pop(connection_id, None)
            online = bool(sessions)
            if not sessions:
                _connections.pop(str(user_id), None)
            return online
    except Exception:
        logger.warning('Presence unavailable; showing unknown status.')
        return None


def is_online(user_id):
    try:
        if settings.REDIS_URL:
            return bool(redis_client(settings.REDIS_URL).zcount(
                f'realtime:presence:{user_id}', time.time(), '+inf'))
        with _lock:
            sessions = _connections.get(str(user_id), {})
            now = time.time()
            for key, expires in list(sessions.items()):
                if expires <= now:
                    del sessions[key]
            online = bool(sessions)
            if not sessions:
                _connections.pop(str(user_id), None)
            return online
    except Exception:
        logger.warning('Presence unavailable; showing unknown status.')
        return None


def allowed_presence_ids(user_id, requested):
    # No arbitrary rooms: apply the same saved-profile rules as private chat.
    if not isinstance(requested, list) or len(requested) > 100:
        raise ValueError('Invalid presence subscription')
    ids = {str(UUID(value)) for value in requested if isinstance(value, str)}
    User = get_user_model()
    user = User.objects.get(pk=user_id)
    return {str(partner.pk) for partner in User.objects.filter(pk__in=ids, is_active=True)
            if can_chat(user, partner)}
