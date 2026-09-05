import logging
from .models import tbl_notification

logger = logging.getLogger(__name__)

def send_in_app_notification(receiver, message: str, sender=None):
    """
    Utility service to create an in-app notification in tbl_notification.
    
    Args:
        receiver: The User instance receiving the notification.
        message: Notification text payload.
        sender: The User instance that initiated the event (optional; defaults to receiver).
        
    Returns:
        tbl_notification instance or None if failed.
    """
    if not receiver or not message:
        return None

    try:
        sender_user = sender if sender else receiver
        notification = tbl_notification.objects.create(
            receiver_id=receiver,
            sender_id=sender_user,
            notification_message=message,
            notification_state='Unread'
        )
        return notification
    except Exception as exc:
        logger.error(f"[send_in_app_notification] Failed to create notification: {exc}")
        return None
