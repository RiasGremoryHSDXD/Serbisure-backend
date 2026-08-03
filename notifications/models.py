from django.db import models
from django.conf import settings
from django.db.models import CheckConstraint, Q
import uuid

class tbl_notification(models.Model):
    notification_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    sender_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_notifications',
        db_column='sender_id'
    )
    
    receiver_id = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_notifications',
        db_column='receiver_id'
    )
    
    notification_message = models.TextField()
    notification_state = models.CharField(max_length=20, default='Unread')
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tbl_notification'
        constraints = [
            CheckConstraint(
                condition=Q(notification_state__in=['Read', 'Unread']),
                name='valid_notification_state_enum'
            )
        ]
