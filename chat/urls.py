from django.urls import path
from .views import (
    SendMessageView,
    SendImageMessageView,
    ReactMessageView,
    ChatMessageView,
    ChatInboxView,
    MarkMessageReadView,
    DeleteChatMessageView,
    ChatTypingView,
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

    # POST   /api/v1/chat/typing/                        → Broadcast typing status
    path('typing/', ChatTypingView.as_view(), name='chat-typing'),

    # GET    /api/v1/chat/inbox/                         → Get inbox (list of all conversations)
    path('inbox/', ChatInboxView.as_view(), name='chat-inbox'),

    # PATCH  /api/v1/chat/read/<message_id>/             → Mark a message as read
    path('read/<uuid:message_id>/', MarkMessageReadView.as_view(), name='chat-read'),

    # DELETE /api/v1/chat/message/<message_id>/          → Unsend or delete message
    path('message/<str:message_id>/', DeleteChatMessageView.as_view(), name='chat-delete-message'),
]
