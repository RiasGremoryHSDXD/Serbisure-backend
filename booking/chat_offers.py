"""Persist a bilateral offer and its chat reference in one transaction."""
import hashlib
import json
from uuid import UUID
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle
from django.contrib.auth import get_user_model
from .models import tbl_booking
from .serializers import BookingSerializer, BookingDetailSerializer
from .services import lock_participants, ensure_eligible_pair, enforce_pair_cap


class ChatOfferThrottle(UserRateThrottle):
    scope = 'chat_offer'
    rate = '50/d'


class ChatBookingOfferView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatOfferThrottle]

    @transaction.atomic
    def post(self, request):
        try:
            key = UUID(request.headers.get('Idempotency-Key', ''))
            recipient_id = UUID(str(request.data.get('recipient_id', '')))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError({'detail': 'A UUID Idempotency-Key and recipient_id are required.'})
        recipient = get_object_or_404(get_user_model(), pk=recipient_id)
        people = lock_participants(request.user.pk, recipient.pk)
        sender, recipient = people[request.user.pk], people[recipient.pk]
        ensure_eligible_pair(sender, recipient)
        digest = hashlib.sha256(json.dumps(request.data, sort_keys=True, default=str).encode()).hexdigest()
        from chat.models import tbl_chat_message
        from chat.serializers import ChatMessageSerializer
        existing = tbl_booking.objects.filter(poster_id=sender, offer_request_key=key).first()
        if existing:
            if existing.offer_payload_hash != digest:
                raise ValidationError({'detail': 'This request key has already been used for different offer terms.'})
            message = existing.chat_messages.get(is_booking_offer=True, booking_proposal__isnull=True)
            return Response({'booking': BookingDetailSerializer(existing, context={'request': request}).data,
                             'chat_message': ChatMessageSerializer(message, context={'request': request}).data})
        serializer = BookingSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        for field in ('end_time', 'work_days', 'daily_start_time', 'daily_end_time', 'region', 'street'):
            if not serializer.validated_data.get(field):
                raise ValidationError({field: 'Specify this agreed term before sending an offer.'})
        booking = serializer.save(poster_id=sender, recipient_id=recipient,
                                  offer_request_key=key, offer_payload_hash=digest)
        enforce_pair_cap(booking, recipient)
        message = tbl_chat_message.objects.create(sender_id=sender, receiver_id=recipient,
            booking_id=booking, is_booking_offer=True, message_payload='Booking offer: review the agreed terms before accepting.')
        return Response({'booking': BookingDetailSerializer(booking, context={'request': request}).data,
                         'chat_message': ChatMessageSerializer(message, context={'request': request}).data}, status=201)
