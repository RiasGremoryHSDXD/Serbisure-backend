from django.urls import path
from .views import (
    SendMessageView,
    SendImageMessageView,
    ReactMessageView,
    ChatMessageView,
    ChatInboxView,
    MarkMessageReadView
)

urlpatterns = [
    # POST   /api/v1/chat/send/                          → Send a new text message
    path('send/', SendMessageView.as_view(), name='chat-send'),

    # POST   /api/v1/chat/send-image/                    → Upload & send an image message
    path('send-image/', SendImageMessageView.as_view(), name='chat-send-image'),

    # POST   /api/v1/chat/react/<message_id>/            → Toggle emoji reaction on message
    path('react/<uuid:message_id>/', ReactMessageView.as_view(), name='chat-react'),

    # GET    /api/v1/chat/thread/<partner_id>/           → Get conversation thread with a specific user
    path('thread/<uuid:partner_id>/', ChatMessageView.as_view(), name='chat-thread'),

    # GET    /api/v1/chat/inbox/                         → Get inbox (list of all conversations)
    path('inbox/', ChatInboxView.as_view(), name='chat-inbox'),

    # PATCH  /api/v1/chat/read/<message_id>/             → Mark a message as read
    path('read/<uuid:message_id>/', MarkMessageReadView.as_view(), name='chat-read'),
]
