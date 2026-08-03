from rest_framework import serializers
from .models import tbl_booking
from django.utils import timezone

class BookingSerializer(serializers.ModelSerializer):

    class Meta:

        model = tbl_booking
        fields = ['booking_id', 'booking_type', 'booking_status', 'service_category', 'start_time', 'end_time', 'service_address', 'special_instruction', 'poster_id', 'createdAt']
        read_only_fields = ['booking_id', 'booking_status', 'poster_id', 'createdAt']

    def validate_booking_type(self, value):

        if value not in ['short_term', 'long_term']:
            raise serializers.ValidationError("Booking type must be either 'short_term' or 'long_term'")
        return value

    def validate_booking_status(self, value):
        
        if value not in ['Pending', 'Accepted', 'InProgress', 'Completed', 'Cancelled']:
            raise serializers.ValidationError("Booking status must be 'Pending', 'Accepted', 'InProgress', 'Completed', or 'Cancelled'.")
        return value

    def validate(self, data):

        now = timezone.now()
        start_time = data.get('start_time')
        end_time = data.get('end_time')

        if start_time and start_time <= now: 
            raise serializers.ValidationError({"start_time": "Start time must be in the future."})
        
        if end_time and  end_time <= now:
            raise serializers.ValidationError({"end_time": "End time must be in the future."})

        if (start_time and end_time) and end_time <= start_time:
            raise serializers.ValidationError({"end_time": "End time must be strictly after the start time."})

        return data