from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.exceptions import Throttled
from core.utils import check_valid_uuid
from rest_framework import status
from rest_framework.response import Response
from rest_framework import generics
from .serializers import BookingSerializer, BookingFeedSerializer
from .models import tbl_booking
from django.core.cache import cache
from core.utils import check_input_letters
import math 

# Create your views here.

class BookingThrottle(UserRateThrottle):
    rate = '50/d'

class BookingView(generics.CreateAPIView):

    throttle_classes = [BookingThrottle]
    serializer_class = BookingSerializer
    queryset = tbl_booking.objects.all()
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):

        if request.user.verification_status != "Verified":
            return Response({
                "detail": "Only verified user can post"},
                status=status.HTTP_403_FORBIDDEN
            )

        idempotency_key = request.headers.get('Idempotency-Key')

        if not idempotency_key or not check_valid_uuid(idempotency_key):
            return Response({"detail": "The Idempotency-Key header is required and must be a valid UUID v4."},
            status=status.HTTP_400_BAD_REQUEST)

        cached_response = cache.get(idempotency_key)

        if cached_response:
            return Response(cached_response['data'], status=cached_response['status'])
        
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):

            serializer.save(poster_id=request.user)

            response_data = {
                "message" : "Booking posted successfully",
                "data": serializer.data
            }
            response_status = status.HTTP_201_CREATED

            if idempotency_key:
                cache.set(
                    idempotency_key,
                    {'data': response_data, 'status': response_status},
                    timeout=86400 # 86400 seconds = 24 hours
                )

            return Response(
                response_data,
                status=response_status
            )

        return super().create(request, *args, **kwargs)
    
    def throttled(self, request, wait):
        # 3600 seconds = 1 hour
        if wait > 3600:
            time_left = math.ceil(wait / 3600)
            custom_message = f"Too many attempts. Please try again in {time_left} hours."
        else:
            custom_message = f"Too many attempts. Please try again in {math.ceil(wait / 60)} minutes"

        raise Throttled(detail=custom_message)

class BookingFeedView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    serializer_class = BookingFeedSerializer

    def get_queryset(self):

        # Identify the user who is making the request
        current_user = self.request.user

        # Get the base query (I added a filter so we only show 'Pending' bookings in the feed, ignoring completed ones!)
        queryset = tbl_booking.objects.select_related('poster_id').filter(booking_status='Pending')

        # 3. Filter based on their account type!
        if current_user.account_type == 'Homeowner':
            # Homeowners only see posts made by Kasambahays
            queryset = queryset.filter(poster_id__account_type='Kasambahay')
        
        elif current_user.account_type == 'Kasambahay':
            # Kasambahays only see posts made by Homeowners
            queryset = queryset.filter(poster_id__account_type='Homeowner')
        
        # Return the final filtered list, newest first
        return queryset.order_by('-createdAt')