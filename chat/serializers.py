from rest_framework import serializers
from .models import tbl_chat_message, tbl_chat_reaction, ALLOWED_EMOJIS
from django.contrib.auth import get_user_model
from core.utils import get_signed_cloudinary_url
from .services import assert_chat_access
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

    def create(self, validated_data):
        from django.db import transaction
        from .moderation import assert_messaging_allowed
        with transaction.atomic():
            ids = [validated_data['sender_id'].pk, validated_data['receiver_id'].pk]
            people = {u.pk: u for u in User.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
            sender = people[ids[0]]
            assert_chat_access(sender, people[ids[1]])
            assert_messaging_allowed(sender, people[ids[1]])
            return super().create(validated_data)

    def validate(self, attrs):
        request = self.context.get('request')
        receiver = attrs.get('receiver_id')

        # 🚫 Defense-in-depth: Prevent sending message to yourself
        if request and receiver and request.user == receiver:
            raise serializers.ValidationError({"receiver_id": "You cannot send a message to yourself."})

        if request and receiver:
            assert_chat_access(request.user, receiver)
            from .moderation import inspect_outgoing
            original = attrs.get('message_payload', '')
            attrs['message_payload'] = inspect_outgoing(request.user, receiver, original)
            self.language_masked = attrs['message_payload'] != original

        booking = attrs.get('booking_id')
        if booking and booking.recipient_id_id and (not request or
                {request.user.pk, receiver.pk} != {booking.poster_id_id, booking.recipient_id_id}):
            raise serializers.ValidationError({'booking_id': 'Private booking terms are only available to their participants.'})
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

        if request and receiver:
            assert_chat_access(request.user, receiver)
            from .moderation import inspect_outgoing
            original = attrs.get('message_payload', '') or ''
            attrs['message_payload'] = inspect_outgoing(request.user, receiver, original)
            self.language_masked = attrs['message_payload'] != original

        booking = attrs.get('booking_id')
        if booking and booking.recipient_id_id and (not request or
                {request.user.pk, receiver.pk} != {booking.poster_id_id, booking.recipient_id_id}):
            raise serializers.ValidationError({'booking_id': 'Private booking terms are only available to their participants.'})

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
            raise serializers.ValidationError(f"Invalid emoji. Allowed emojis: {' '.join(sorted(ALLOWED_EMOJIS))}")
        return val


class ChatMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for individual messages in a conversation thread.
    Includes sender indicator, image signed URL, reaction summary, and personal reaction.
    """
    is_sender = serializers.SerializerMethodField()
    booking_offer = serializers.SerializerMethodField()
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
            'booking_offer',
            'reaction_summary',
            'my_reaction',
            'createdAt'
        ]

    def get_booking_offer(self, obj):
        if not obj.is_booking_offer or not obj.booking_id:
            return None
        request = self.context.get('request')
        if not request or request.user.pk not in (obj.sender_id_id, obj.receiver_id_id):
            return None
        from booking.serializers import BookingDetailSerializer
        booking = obj.booking_id
        proposal = obj.booking_proposal
        assignment = booking.assignments.first()
        pair = {obj.sender_id_id, obj.receiver_id_id}
        confirmed = (booking.booking_status in ('Accepted', 'InProgress', 'Completed')
                     and assignment is not None and {booking.poster_id_id, assignment.accepter_id_id} == pair
                     and (proposal is None or proposal.status == 'Accepted'))
        can_respond = booking.booking_status == 'Pending' and (
            (proposal is not None and proposal.status == 'Pending' and request.user.pk == booking.poster_id_id)
            or (proposal is None and request.user.pk == booking.recipient_id_id))
        return {'booking': BookingDetailSerializer(booking, context={'request': request}).data,
                'proposal_id': str(proposal.pk) if proposal else None,
                'proposed_rate': str(proposal.proposed_rate) if proposal else None,
                'status': 'Confirmed' if confirmed else proposal.status if proposal else booking.booking_status,
                'can_respond': can_respond,
                'sender_name': (obj.sender_id.first_name + ' ' + obj.sender_id.last_name).strip() or obj.sender_id.username}

    def get_is_sender(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.sender_id_id == request.user.id
        return False

    def get_image_url(self, obj):
        if obj.message_type != 'image' or not obj.image_public_id:
            return None
        return get_signed_cloudinary_url(obj.image_public_id, as_avatar=False)

    def get_reaction_summary(self, obj):
        counts = {e: 0 for e in ALLOWED_EMOJIS}
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
    sent_count = serializers.IntegerField(default=0)

    def get_partner_profile_image(self, obj):
        return get_signed_cloudinary_url(obj.get('partner_profile_link'), as_avatar=True)


class SupportContactSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.SerializerMethodField()
    account_type = serializers.CharField()
    barangay = serializers.CharField(allow_blank=True, allow_null=True)
    avatar = serializers.SerializerMethodField()

    def get_name(self, obj):
        return obj.get_full_name().strip() or obj.username

    def get_avatar(self, obj):
        return get_signed_cloudinary_url(obj.profile_link, as_avatar=True)


class BarangaySupportSerializer(serializers.Serializer):
    name = serializers.CharField(allow_blank=True)
    available = serializers.BooleanField()
    contacts = SupportContactSerializer(many=True)
    message = serializers.CharField(allow_blank=True)


class SupportContactsSerializer(serializers.Serializer):
    superadmins = SupportContactSerializer(many=True)
    barangay = BarangaySupportSerializer()


class MarkMessageReadSerializer(serializers.ModelSerializer):
    """
    Serializer for marking a message as read.
    """
    class Meta:
        model = tbl_chat_message
        fields = ['chat_message_id', 'is_read']
        read_only_fields = ['chat_message_id']
