"""HTTP API and authenticated personal WebSocket streams share the same ASGI server."""
import os
from django.core.asgi import get_asgi_application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Serbisure.settings')
django_application = get_asgi_application()
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from realtime.consumers import UserEventsConsumer
application = ProtocolTypeRouter({
    'http': django_application,
    'websocket': URLRouter([path('ws/events/', UserEventsConsumer.as_asgi())]),
})
