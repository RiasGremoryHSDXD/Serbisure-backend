from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken
from django.db.models import CheckConstraint, Q, F
from django.db.models.expressions import RawSQL
import base64
import hashlib
import uuid


def _get_cipher():
    """
        Derives a safe 32-byte Fernet key from Django's SECRET_KEY.
    """
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)

class EncryptedTextField(models.TextField):

    def from_db_value(self, value, expressions, connection):
        if not value:
            return value
        
        try:
            return _get_cipher().decrypt(value.encode('utf-8')).decode('utf-8')

        except (InvalidToken, Exception):
            return value

    def to_python(self, value):
        if not value:
            return value
        return str(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)

        if not value:
            return value
        return _get_cipher().encrypt(value.encode('utf-8')).decode('utf-8')


MESSAGE_TYPE_CHOICES = [
    ('text', 'Text'),
    ('image', 'Image'),
]

ALLOWED_EMOJIS = {'❤️', '👍', '😂', '😢', '😮'}


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
    
    booking_id = models.ForeignKey(
        'booking.tbl_booking',
        on_delete=models.CASCADE,
        related_name='chat_messages',
        db_column='booking_id',
        null=True,
        blank=True
    )

    message_type = models.CharField(
        max_length=10,
        choices=MESSAGE_TYPE_CHOICES,
        default='text'
    )

    image_public_id = models.CharField(
        max_length=500,
        blank=True,
        null=True
    )

    message_payload = EncryptedTextField(
        max_length=500,
        blank=True,
        null=True
    )

    is_read = models.BooleanField(
        default=False
    )

    is_deleted = models.BooleanField(
        default=False
    )

    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tbl_chat_message'

        constraints = [
            CheckConstraint(
                condition=~Q(sender_id=F('receiver_id')),
                name='sender_cannot_be_receiver'
            ),

            CheckConstraint(
                condition=(
                    Q(message_type='image') |
                    RawSQL("length(trim(message_payload)) > 0", [], output_field=models.BooleanField())
                ),
                name='message_payload_not_empty_or_whitespace'
            ),

            CheckConstraint(
                condition=(
                    Q(message_type='image') |
                    Q(image_public_id__isnull=True)
                ),
                name='text_message_cannot_have_image_public_id'
            ),
        ]


class tbl_chat_reaction(models.Model):
    reaction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    message = models.ForeignKey(
        tbl_chat_message,
        on_delete=models.CASCADE,
        related_name='reactions',
        db_column='message_id'
    )
    reactor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_reactions',
        db_column='reactor_id'
    )
    emoji = models.CharField(max_length=10)
    reacted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tbl_chat_reaction'
        constraints = [
            models.UniqueConstraint(
                fields=['message', 'reactor'],
                name='one_reaction_per_user_per_message'
            )
        ]

