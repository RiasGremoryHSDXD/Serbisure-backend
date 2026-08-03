from django.db import models
from django.conf import settings
import uuid

class tbl_chat_message(models.Model):
    chat_message_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    sender_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages',
        db_column='sender_id'
    )
    
    receiver_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_messages',
        db_column='receiver_id'
    )
    
    message_payload = models.TextField()
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tbl_chat_message'
