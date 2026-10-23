"""Small read-only readiness check for the HTTP service and its dependencies."""
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe
from redis import Redis


@require_safe
def readiness(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        if settings.REDIS_URL:
            with Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2) as client:
                client.ping()
    except Exception:
        response = JsonResponse({'status': 'unavailable'}, status=503)
    else:
        response = JsonResponse({'status': 'ok'})
    response['Cache-Control'] = 'no-store'
    return response
