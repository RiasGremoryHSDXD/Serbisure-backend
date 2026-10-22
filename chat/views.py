from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from realtime.events import chat_changed, publish
from realtime.presence import is_online
from django.db.models import Q
from django.shortcuts import get_object_or_404
from core.utils import check_valid_uuid, get_signed_cloudinary_url
from .models import tbl_chat_message, tbl_chat_reaction, ALLOWED_EMOJIS
from .services import assert_chat_access, assert_message_access, can_chat, support_contacts, remove_message_for_user
from .serializers import (
    SendMessageSerializer,
    SendImageMessageSerializer,
    ReactMessageSerializer,
    ChatMessageSerializer,
    ChatInboxSerializer,
    MarkMessageReadSerializer,
    SupportContactsSerializer,
)
import math
import re
import cloudinary.utils
import cloudinary.uploader

User = get_user_model()


# ─────────────────────────────────────────────
# Throttle Classes
# ─────────────────────────────────────────────

class SendMessageThrottle(UserRateThrottle):
    scope = 'chat_send'
    rate = '60/m'


class ChatMessageThrottle(UserRateThrottle):
    scope = 'chat_messages'
    rate = '120/m'


class ChatInboxThrottle(UserRateThrottle):
    scope = 'chat_inbox'
    rate = '60/m'


class ChatTypingThrottle(UserRateThrottle):
    scope = 'chat_typing'


class MarkMessageReadThrottle(UserRateThrottle):
    scope = 'chat_read'
    rate = '60/m'


class ChatImageUploadThrottle(UserRateThrottle):
    scope = 'chat_image_upload'
    rate = '20/h'


class ChatReactThrottle(UserRateThrottle):
    scope = 'chat_react'
    rate = '120/h'


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def _get_throttle_message(wait):
    """Returns a standardized throttle message based on wait time in seconds."""
    if wait > 3600:
        time_left = math.ceil(wait / 3600)
        return f"Too many requests. Please try again in {time_left} hours."
    return f"Too many requests. Please try again in {math.ceil(wait / 60)} minutes."


class SupportContactsView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatInboxThrottle]
    serializer_class = SupportContactsSerializer

    def get(self, request):
        response = Response(self.get_serializer(support_contacts(request.user)).data)
        response['Cache-Control'] = 'private, no-store'
        return response


# ─────────────────────────────────────────────
# POST /api/v1/chat/send/
# ─────────────────────────────────────────────

class SendMessageView(generics.CreateAPIView):
    """
    Sends a new text message to another user.
    Requires a valid UUIDv4 Idempotency-Key header to prevent duplicate messages on network retry.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [SendMessageThrottle]
    serializer_class = SendMessageSerializer

    def create(self, request, *args, **kwargs):
        # Step 1: Validate Idempotency-Key header
        idempotency_key = request.headers.get('Idempotency-Key')

        if not idempotency_key or not check_valid_uuid(idempotency_key):
            return Response(
                {"detail": "The Idempotency-Key header is required and must be a valid UUID v4."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 2: Check cache — prevent duplicate sends on network retry
        # Authorize against the current saved profiles even on a cached retry.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cached_response = cache.get(f'chat_send_{request.user.pk}_{idempotency_key}')
        if cached_response:
            return Response(cached_response['data'], status=cached_response['status'])

        chat_msg = serializer.save(sender_id=request.user)

        # In-App Notification Trigger
        try:
            from notifications.services import send_in_app_notification
            sender_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
            send_in_app_notification(
                receiver=chat_msg.receiver_id,
                sender=request.user,
                message=f"New message from {sender_name}."
            )
        except Exception:
            pass

        response_data = {
            "message": "Message sent successfully.",
            "data": serializer.data
        }
        from .moderation import LANGUAGE_NOTICE
        response_data['language_warning'] = LANGUAGE_NOTICE if getattr(serializer, 'language_masked', False) else None
        response_status = status.HTTP_201_CREATED

        # Store in cache for 1 hour (idempotency window).
        cache.set(
            f'chat_send_{request.user.pk}_{idempotency_key}',
            {'data': response_data, 'status': response_status},
            timeout=3600
        )

        return Response(response_data, status=response_status)

    def throttled(self, request, wait):
        raise Throttled(detail=_get_throttle_message(wait))


# ─────────────────────────────────────────────
# POST /api/v1/chat/send-image/
# ─────────────────────────────────────────────

class SendImageMessageView(generics.CreateAPIView):
    """
    Uploads and sends an image attachment message.
    Requires a valid UUIDv4 Idempotency-Key header to prevent duplicate Cloudinary uploads on retry.
    Accepts multipart/form-data with image, receiver_id, optional booking_id, and optional message_payload (caption).
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatImageUploadThrottle]
    serializer_class = SendImageMessageSerializer
    parser_classes = [MultiPartParser, FormParser]

    def create(self, request, *args, **kwargs):
        # Step 1: Validate Idempotency-Key header
        idempotency_key = request.headers.get('Idempotency-Key')

        if not idempotency_key or not check_valid_uuid(idempotency_key):
            return Response(
                {"detail": "The Idempotency-Key header is required and must be a valid UUID v4."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 3: Check recipient user before upload (Edge Case #10, #11)
        receiver_raw = request.data.get('receiver_id')
        if not receiver_raw or not check_valid_uuid(str(receiver_raw)):
            return Response(
                {"receiver_id": ["Invalid or missing recipient UUID."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        if str(receiver_raw) == str(request.user.id):
            return Response(
                {"receiver_id": ["You cannot send a message to yourself."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            receiver_user = User.objects.get(id=receiver_raw)
        except User.DoesNotExist:
            return Response(
                {"detail": "Recipient user not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        assert_chat_access(request.user, receiver_user)
        from .moderation import assert_messaging_allowed
        assert_messaging_allowed(request.user, receiver_user)
        cached_response = cache.get(f'chat_send_image_{request.user.pk}_{idempotency_key}')
        if cached_response:
            return Response(cached_response['data'], status=cached_response['status'])

        # Step 4: Check image file input exists (Edge Case #5, #12)
        if 'image' not in request.FILES:
            return Response(
                {"image": ["No image file was provided."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(request.FILES.getlist('image')) > 1:
            return Response(
                {"detail": "Only a single image upload is allowed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 5: Validate serializer input (size <= 10MB, not empty, not SVG, magic bytes, caption <= 200)
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        image_file = validated_data['image']
        caption = validated_data.get('message_payload', '')
        booking = validated_data.get('booking_id')

        # Step 6: Upload to Cloudinary (Edge Case #9)
        try:
            upload_result = cloudinary.uploader.upload(
                image_file,
                folder="serbisure_chat_images/",
                type="authenticated"
            )
        except Exception:
            return Response(
                {"detail": "Image storage is temporarily unavailable. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY
            )

        public_id = upload_result.get('public_id')
        if not public_id:
            return Response(
                {"detail": "Failed to obtain image asset identifier."},
                status=status.HTTP_502_BAD_GATEWAY
            )

        # Step 7: Check image dimensions (Pixel bomb defense - Edge Case #3)
        width = upload_result.get('width', 0)
        height = upload_result.get('height', 0)
        if width > 10000 or height > 10000:
            try:
                cloudinary.uploader.destroy(public_id, type="authenticated")
            except Exception:
                pass
            return Response(
                {"detail": "Image dimensions are too large. Maximum dimensions are 10000x10000 pixels."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Recheck under the same account lock used for moderation decisions: a
        # restriction applied during an upload must not let the image through.
        try:
            from .moderation import assert_messaging_allowed
            with transaction.atomic():
                people = {u.pk: u for u in User.objects.select_for_update().filter(
                    pk__in=[request.user.pk, receiver_user.pk]).order_by('pk')}
                sender = people[request.user.pk]
                receiver_user = people[receiver_user.pk]
                assert_chat_access(sender, receiver_user)
                assert_messaging_allowed(sender, receiver_user)
                chat_msg = tbl_chat_message.objects.create(
                    sender_id=sender, receiver_id=receiver_user, booking_id=booking,
                    message_type='image', image_public_id=public_id, message_payload=caption or None)
        except Exception:
            try:
                cloudinary.uploader.destroy(public_id, type='authenticated')
            except Exception:
                pass
            raise

        # Step 9: In-app notification
        try:
            from notifications.services import send_in_app_notification
            sender_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
            send_in_app_notification(
                receiver=chat_msg.receiver_id,
                sender=request.user,
                message=f"New photo from {sender_name}."
            )
        except Exception:
            pass

        # Step 10: Serialize response
        out_serializer = ChatMessageSerializer(chat_msg, context={'request': request})
        response_data = {
            "message": "Image sent successfully.",
            "data": out_serializer.data
        }
        from .moderation import LANGUAGE_NOTICE
        response_data['language_warning'] = LANGUAGE_NOTICE if getattr(serializer, 'language_masked', False) else None
        response_status = status.HTTP_201_CREATED

        # Step 11: Store in cache for 1 hour
        cache.set(
            f'chat_send_image_{request.user.pk}_{idempotency_key}',
            {'data': response_data, 'status': response_status},
            timeout=3600
        )

        return Response(response_data, status=response_status)

    def throttled(self, request, wait):
        raise Throttled(detail=_get_throttle_message(wait))


# ─────────────────────────────────────────────
# POST /api/v1/chat/react/<uuid:message_id>/
# ─────────────────────────────────────────────

class ReactMessageView(generics.GenericAPIView):
    """
    Toggles an emoji reaction on a message.
    - No existing reaction: creates one (action: 'added')
    - Same emoji exists: deletes it (action: 'removed')
    - Different emoji exists: updates it (action: 'changed')
    Only conversation participants can react.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatReactThrottle]
    serializer_class = ReactMessageSerializer

    def post(self, request, message_id, *args, **kwargs):
        # Step 1: Validate message UUID
        if not message_id or not check_valid_uuid(str(message_id)):
            return Response(
                {"detail": "Invalid or missing message UUID."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 2: Fetch message (Edge Case #20, #21: deleted or non-existent -> 404)
        try:
            message = tbl_chat_message.objects.get(chat_message_id=message_id, is_deleted=False)
        except tbl_chat_message.DoesNotExist:
            return Response(
                {"detail": "Message not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Step 3: Authorization guard (Edge Case #19)
        if request.user.id not in (message.sender_id_id, message.receiver_id_id):
            return Response(
                {"detail": "You are not a participant of this conversation."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Step 4: Validate request body (Edge Case #16, #17, #18, #25)
        assert_message_access(request.user, message)
        hidden = message.hidden_by_sender if message.sender_id_id == request.user.pk else message.hidden_by_receiver
        if hidden:
            return Response({'detail': 'Message not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        emoji = serializer.validated_data['emoji']

        # Step 5: Toggle logic with race condition defense (Edge Case #22)
        action = "added"
        my_reaction = emoji

        with transaction.atomic():
            reaction = tbl_chat_reaction.objects.filter(
                message=message,
                reactor=request.user
            ).select_for_update().first()

            if reaction:
                current_emoji = '❤️' if reaction.emoji == '\u2764' else reaction.emoji
                if current_emoji == emoji:
                    reaction.delete()
                    action = "removed"
                    my_reaction = None
                else:
                    reaction.emoji = emoji
                    reaction.save(update_fields=['emoji'])
                    action = "changed"
                    my_reaction = emoji
            else:
                try:
                    tbl_chat_reaction.objects.create(
                        message=message,
                        reactor=request.user,
                        emoji=emoji
                    )
                    action = "added"
                    my_reaction = emoji
                except IntegrityError:
                    # Caught concurrent insert
                    reaction = tbl_chat_reaction.objects.filter(
                        message=message,
                        reactor=request.user
                    ).first()
                    if reaction:
                        current_emoji = '❤️' if reaction.emoji == '\u2764' else reaction.emoji
                        if current_emoji == emoji:
                            reaction.delete()
                            action = "removed"
                            my_reaction = None
                        else:
                            reaction.emoji = emoji
                            reaction.save(update_fields=['emoji'])
                            action = "changed"
                            my_reaction = emoji

        # Step 6: Compute counts
        counts = {e: 0 for e in ALLOWED_EMOJIS}
        for r in tbl_chat_reaction.objects.filter(message=message):
            e = '❤️' if r.emoji == '\u2764' else r.emoji
            if e in counts:
                counts[e] += 1

        return Response({
            "message": "Reaction updated.",
            "action": action,
            "data": {
                "message_id": str(message.chat_message_id),
                "my_reaction": my_reaction,
                "reaction_counts": counts
            }
        }, status=status.HTTP_200_OK)

    def throttled(self, request, wait):
        raise Throttled(detail=_get_throttle_message(wait))


# ─────────────────────────────────────────────
# GET /api/v1/chat/thread/<uuid:partner_id>/
# ─────────────────────────────────────────────

class ChatMessageView(generics.ListAPIView):
    """
    Retrieves the paginated two-way conversation thread
    between the authenticated user and a specific partner.
    Oldest messages first (top-to-bottom reading order).
    Uses prefetch_related on reactions to prevent N+1 queries.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatMessageThrottle]
    serializer_class = ChatMessageSerializer

    def get_queryset(self):
        partner_id = self.kwargs.get('partner_id')
        current_user = self.request.user

        # Validate partner UUID
        if not partner_id or not check_valid_uuid(str(partner_id)):
            raise ValidationError({"detail": "Invalid or missing partner UUID."})

        partner = get_object_or_404(User, pk=partner_id)
        assert_chat_access(current_user, partner)

        # Authorization guard: Fetch only messages between these two users
        return tbl_chat_message.objects.visible_to(current_user).filter(
            Q(sender_id=current_user, receiver_id=partner_id) |
            Q(sender_id=partner_id, receiver_id=current_user),
            is_deleted=False
        ).select_related('sender_id', 'receiver_id', 'booking_id', 'booking_id__poster_id', 'booking_id__recipient_id', 'booking_proposal').prefetch_related('reactions').order_by('createdAt')

    def list(self, request, *args, **kwargs):
        partner_id = self.kwargs.get('partner_id')
        # Check access before marking any messages read or publishing receipts.
        queryset = self.filter_queryset(self.get_queryset())
        if partner_id and check_valid_uuid(str(partner_id)):
            read_count = tbl_chat_message.objects.visible_to(request.user).filter(
                sender_id=partner_id,
                receiver_id=request.user,
                is_read=False,
                is_deleted=False
            ).update(is_read=True)
            if read_count:
                chat_changed(partner_id, request.user.pk)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
        else:
            serializer = self.get_serializer(queryset, many=True)
            response = Response({"data": serializer.data})

        if partner_id and check_valid_uuid(str(partner_id)):
            cache_key = f'chat_typing_{partner_id}_{request.user.id}'
            is_partner_typing = bool(cache.get(cache_key))
            is_partner_online = is_online(partner_id)
            if isinstance(response.data, dict):
                response.data['partner_is_typing'] = is_partner_typing
                response.data['partner_is_online'] = is_partner_online
            response['X-Partner-Is-Typing'] = 'true' if is_partner_typing else 'false'
            if is_partner_online is not None:
                response['X-Partner-Is-Online'] = 'true' if is_partner_online else 'false'

        return response

    def throttled(self, request, wait):
        raise Throttled(detail=_get_throttle_message(wait))


# ─────────────────────────────────────────────
# GET /api/v1/chat/inbox/
# ─────────────────────────────────────────────

class ChatInboxView(generics.GenericAPIView):
    """
    Returns a list of unique conversation partners for the authenticated user.
    Each item shows: partner info, last message preview, timestamp, and unread count.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatInboxThrottle]
    serializer_class = ChatInboxSerializer

    def get(self, request, *args, **kwargs):
        current_user = request.user

        # Step 1: Find all unique partner IDs this user has talked to
        visible_messages = tbl_chat_message.objects.visible_to(current_user)
        sent_to = visible_messages.filter(
            sender_id=current_user,
            is_deleted=False
        ).values_list('receiver_id', flat=True).distinct()

        received_from = visible_messages.filter(
            receiver_id=current_user,
            is_deleted=False
        ).values_list('sender_id', flat=True).distinct()

        # Merge both directions into a unique set of partner IDs
        partner_ids = set(list(sent_to) + list(received_from))

        inbox = []

        for partner in User.objects.filter(pk__in=partner_ids, is_active=True):
            if not can_chat(current_user, partner):
                continue

            # Step 2: Get most recent message in the conversation
            last_msg = visible_messages.filter(
                Q(sender_id=current_user, receiver_id=partner) |
                Q(sender_id=partner, receiver_id=current_user),
                is_deleted=False
            ).order_by('-createdAt').first()

            if not last_msg:
                continue

            # Step 3: Count unread messages from this partner
            unread_count = visible_messages.filter(
                sender_id=partner,
                receiver_id=current_user,
                is_read=False,
                is_deleted=False
            ).count()

            sent_count = visible_messages.filter(
                sender_id=current_user,
                receiver_id=partner,
                is_deleted=False
            ).count()

            # Step 4: Build Cloudinary signed URL (Optimized WebP)
            partner_profile_image = get_signed_cloudinary_url(getattr(partner, 'profile_link', None), as_avatar=True)

            # Format preview text for text vs image messages
            raw_payload = last_msg.message_payload or ""
            from .moderation_rules import contains_offensive_language
            if last_msg.sender_id_id != request.user.pk and contains_offensive_language(raw_payload):
                raw_payload = 'Sensitive message'
            # Both text replies and photo captions use the mobile-compatible quote prefix.
            match = re.match(r'^> \[[^\]]+\]:\s*.*?\n\n([\s\S]*)$', raw_payload)
            clean_payload = match.group(1).strip() if match else raw_payload
            if last_msg.message_type == 'image':
                last_message_text = f"📷 {clean_payload}" if clean_payload else "📷 Photo"
            else:
                if last_msg.sender_id == current_user:
                    last_message_text = f"You: {clean_payload}" if clean_payload else "You sent a message"
                else:
                    last_message_text = clean_payload or ""

            inbox.append({
                'partner_id': partner.id,
                'partner_name': f"{partner.first_name} {partner.last_name}".strip(),
                'partner_account_type': partner.account_type,
                'partner_profile_link': partner_profile_image,
                'last_message': last_message_text,
                'last_message_time': last_msg.createdAt,
                'unread_count': unread_count,
                'sent_count': sent_count,
            })

        # Step 5: Sort inbox by most recent message
        inbox.sort(key=lambda x: x['last_message_time'], reverse=True)

        serializer = self.get_serializer(inbox, many=True)
        return Response({
            "message": "Inbox retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def throttled(self, request, wait):
        raise Throttled(detail=_get_throttle_message(wait))


# ─────────────────────────────────────────────
# PATCH /api/v1/chat/read/<uuid:message_id>/
# ─────────────────────────────────────────────

class MarkMessageReadView(generics.UpdateAPIView):
    """
    Marks a specific message as read.
    Only the intended receiver of the message can mark it as read.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [MarkMessageReadThrottle]
    serializer_class = MarkMessageReadSerializer
    http_method_names = ['patch']

    def get_object(self):
        message_id = self.kwargs.get('message_id')

        # Validate message_id UUID
        if not message_id or not check_valid_uuid(str(message_id)):
            raise ValidationError({"detail": "Invalid or missing message UUID."})

        try:
            message = tbl_chat_message.objects.visible_to(self.request.user).get(chat_message_id=message_id)
        except tbl_chat_message.DoesNotExist:
            raise ValidationError({"detail": "Message not found."})

        # Authorization guard: Only the receiver can mark as read
        if message.receiver_id != self.request.user:
            raise ValidationError({"detail": "You are not authorized to mark this message as read."})

        assert_message_access(self.request.user, message)

        return message

    def patch(self, request, *args, **kwargs):
        message = self.get_object()

        if message.is_read:
            return Response(
                {"message": "Message is already marked as read."},
                status=status.HTTP_200_OK
            )

        message.is_read = True
        message.save(update_fields=['is_read'])

        return Response(
            {"message": "Message marked as read successfully."},
            status=status.HTTP_200_OK
        )

    def throttled(self, request, wait):
        raise Throttled(detail=_get_throttle_message(wait))


# ─────────────────────────────────────────────
# DELETE /api/v1/chat/message/<uuid:message_id>/
# ─────────────────────────────────────────────

class DeleteChatMessageView(generics.GenericAPIView):
    """
    Removes a message only from the authenticated participant's devices.
    Message content and the other participant's visibility are preserved.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatMessageThrottle]

    @transaction.atomic
    def delete(self, request, message_id, *args, **kwargs):
        clean_id = str(message_id).strip().rstrip('/')

        # If it's a temp/mock client ID (not a valid UUID), treat as successfully handled
        if not clean_id or not check_valid_uuid(clean_id):
            return Response({
                "message": "Message removed.",
                "data": {"message_id": str(clean_id)}
            }, status=status.HTTP_200_OK)

        try:
            message = tbl_chat_message.objects.select_for_update().get(chat_message_id=clean_id, is_deleted=False)
        except tbl_chat_message.DoesNotExist:
            # Idempotent response: If already deleted or not found, return 200 OK so client does not error
            return Response({
                "message": "Message already deleted or removed.",
                "data": {"message_id": str(clean_id)}
            }, status=status.HTTP_200_OK)

        # Authorization guard: Only participants can delete
        if request.user.id not in (message.sender_id_id, message.receiver_id_id):
            return Response(
                {"detail": "You are not authorized to delete this message."},
                status=status.HTTP_403_FORBIDDEN
            )

        remove_message_for_user(request.user, message)

        return Response({
            "message": "Message removed for you.",
            "data": {
                "message_id": str(clean_id)
            }
        }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────
# POST /api/v1/chat/typing/
# ─────────────────────────────────────────────

class ChatTypingView(generics.GenericAPIView):
    """
    Broadcasts typing indicator status to conversation partner.
    Cached with short TTL (5 seconds).
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatTypingThrottle]

    def post(self, request, *args, **kwargs):
        partner_id = request.data.get('partner_id')
        is_typing = request.data.get('is_typing', True)
        if not isinstance(is_typing, bool):
            raise ValidationError({'detail': 'is_typing must be a boolean.'})
        if not partner_id or not check_valid_uuid(str(partner_id)):
            raise ValidationError({'detail': 'A valid partner UUID is required.'})
        from django.contrib.auth import get_user_model
        partner = get_user_model().objects.filter(pk=partner_id, is_active=True).first()
        if not partner:
            raise ValidationError({'detail': 'This typing target is not permitted.'})
        assert_chat_access(request.user, partner)
        if is_typing:
            from .moderation import assert_messaging_allowed
            assert_messaging_allowed(request.user, partner)
        if partner_id:
            cache_key = f'chat_typing_{request.user.id}_{partner_id}'
            if is_typing:
                cache.set(cache_key, True, timeout=5)
            else:
                cache.delete(cache_key)
            publish([partner_id], {'type': 'chat.typing', 'partner_id': str(request.user.pk), 'is_typing': bool(is_typing)})
        return Response({"status": "ok"}, status=status.HTTP_200_OK)

