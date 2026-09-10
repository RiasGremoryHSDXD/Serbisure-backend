from rest_framework import serializers
from .models import tbl_chat_message, tbl_chat_reaction, ALLOWED_EMOJIS
from django.contrib.auth import get_user_model
import cloudinary.utils
import time

User = get_user_model()


class SendMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for validating and creating new text chat messages.
    """
    message_payload = serializers.CharField(
        max_length=500,
        required=True,
        allow_blank=False,
        error_messages={
            "blank": "Message content cannot be empty.",
            "max_length": "Message cannot exceed 500 characters."
        }
    )

    class Meta:
        model = tbl_chat_message
        fields = [
            'chat_message_id',
            'sender_id',
            'receiver_id',
            'booking_id',
            'message_payload',
            'is_read',
            'createdAt'
        ]
        read_only_fields = ['chat_message_id', 'sender_id', 'is_read', 'createdAt']

    def validate_message_payload(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Message content cannot be blank or whitespace only.")
        return stripped

    def validate(self, attrs):
        request = self.context.get('request')
        receiver = attrs.get('receiver_id')

        # 🚫 Defense-in-depth: Prevent sending message to yourself
        if request and receiver and request.user == receiver:
            raise serializers.ValidationError({"receiver_id": "You cannot send a message to yourself."})

        return attrs


class SendImageMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for validating image attachments and optional captions.
    """
    image = serializers.FileField(
        required=True,
        write_only=True,
        error_messages={
            "required": "No image file was provided.",
            "empty": "Uploaded image is empty.",
            "null": "No image file was provided."
        }
    )
    message_payload = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
        allow_null=True,
        default='',
        error_messages={
            "max_length": "Caption cannot exceed 200 characters."
        }
    )

    class Meta:
        model = tbl_chat_message
        fields = [
            'chat_message_id',
            'sender_id',
            'receiver_id',
            'booking_id',
            'message_payload',
            'image',
            'is_read',
            'createdAt'
        ]
        read_only_fields = ['chat_message_id', 'sender_id', 'is_read', 'createdAt']

    def validate_image(self, value):
        if not value:
            raise serializers.ValidationError("No image file was provided.")

        # Check empty file (Edge Case #6)
        if getattr(value, 'size', 0) == 0:
            raise serializers.ValidationError("Uploaded image is empty.")

        # Check file size max 10MB (Edge Case #4)
        max_size = 10 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("Image must be smaller than 10 MB.")

        # Check SVG explicitly (Edge Case #2)
        content_type = getattr(value, 'content_type', '') or ''
        name = getattr(value, 'name', '') or ''
        if 'svg' in content_type.lower() or name.lower().endswith('.svg'):
            raise serializers.ValidationError("SVG images are not supported.")

        # Check magic bytes for JPEG, PNG, WEBP (Edge Case #1)
        pos = value.tell() if hasattr(value, 'tell') else 0
        header = value.read(16)
        if hasattr(value, 'seek'):
            value.seek(pos)

        if len(header) < 12:
            raise serializers.ValidationError("File is too small to be a valid image.")

        is_jpeg = header.startswith(b'\xff\xd8\xff')
        is_png = header.startswith(b'\x89PNG')
        is_webp = header.startswith(b'RIFF') and header[8:12] == b'WEBP'

        if not (is_jpeg or is_png or is_webp):
            raise serializers.ValidationError("Unsupported image format. Only JPEG, PNG, and WEBP are allowed.")

        return value

    def validate_message_payload(self, value):
        if not value:
            return ''
        if '\x00' in value:
            raise serializers.ValidationError("Caption contains invalid characters.")
        stripped = value.strip()
        if len(stripped) > 200:
            raise serializers.ValidationError("Caption cannot exceed 200 characters.")
        return stripped

    def validate(self, attrs):
        request = self.context.get('request')
        receiver = attrs.get('receiver_id')

        # 🚫 Prevent sending message to yourself (Edge Case #10)
        if request and receiver and request.user == receiver:
            raise serializers.ValidationError({"receiver_id": "You cannot send a message to yourself."})

        return attrs


class ReactMessageSerializer(serializers.Serializer):
    """
    Serializer for toggling an emoji reaction on a chat message.
    """
    emoji = serializers.CharField(
        max_length=10,
        required=True,
        allow_blank=False,
        allow_null=False,
        error_messages={
            "blank": "Emoji cannot be blank.",
            "required": "Emoji is required."
        }
    )

    def validate_emoji(self, value):
        if not isinstance(value, str):
            raise serializers.ValidationError("Not a valid string.")
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Emoji cannot be blank.")
        if val == '\u2764':
            val = '❤️'
        if val not in ALLOWED_EMOJIS:
            raise serializers.ValidationError("Invalid emoji. Allowed emojis: ❤️ 👍 😂 😢 😮")
        return val


class ChatMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for individual messages in a conversation thread.
    Includes sender indicator, image signed URL, reaction summary, and personal reaction.
    """
    is_sender = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    reaction_summary = serializers.SerializerMethodField()
    my_reaction = serializers.SerializerMethodField()

    class Meta:
        model = tbl_chat_message
        fields = [
            'chat_message_id',
            'sender_id',
            'receiver_id',
            'booking_id',
            'message_type',
            'image_public_id',
            'image_url',
            'message_payload',
            'is_read',
            'is_sender',
            'reaction_summary',
            'my_reaction',
            'createdAt'
        ]

    def get_is_sender(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.sender_id_id == request.user.id
        return False

    def get_image_url(self, obj):
        if obj.message_type != 'image' or not obj.image_public_id:
            return None
        try:
            url, _ = cloudinary.utils.cloudinary_url(
                obj.image_public_id,
                type='authenticated',
                sign_url=True,
                expires_at=int(time.time()) + 3600
            )
            return url
        except Exception:
            return None

    def get_reaction_summary(self, obj):
        counts = {'❤️': 0, '👍': 0, '😂': 0, '😢': 0, '😮': 0}
        try:
            for r in obj.reactions.all():
                emoji = '❤️' if r.emoji == '\u2764' else r.emoji
                if emoji in counts:
                    counts[emoji] += 1
        except Exception:
            pass
        return counts

    def get_my_reaction(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        try:
            for r in obj.reactions.all():
                if r.reactor_id == request.user.id:
                    return '❤️' if r.emoji == '\u2764' else r.emoji
        except Exception:
            pass
        return None


class ChatInboxSerializer(serializers.Serializer):
    """
    Serializer for the conversation list (inbox).
    """
    partner_id = serializers.UUIDField()
    partner_name = serializers.CharField()
    partner_account_type = serializers.CharField()
    partner_profile_image = serializers.SerializerMethodField()
    last_message = serializers.CharField(allow_blank=True, allow_null=True)
    last_message_time = serializers.DateTimeField()
    unread_count = serializers.IntegerField(default=0)

    def get_partner_profile_image(self, obj):
        public_id = obj.get('partner_profile_link')
        if not public_id:
            return None

        try:
            temporary_url, _ = cloudinary.utils.cloudinary_url(
                public_id,
                type="authenticated",
                sign_url=True
            )
            return temporary_url
        except Exception:
            return None


class MarkMessageReadSerializer(serializers.ModelSerializer):
    """
    Serializer for marking a message as read.
    """
    class Meta:
        model = tbl_chat_message
        fields = ['chat_message_id', 'is_read']
        read_only_fields = ['chat_message_id']
