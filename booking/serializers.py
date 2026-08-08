from rest_framework import serializers
from .models import tbl_booking
from django.utils import timezone

class BookingSerializer(serializers.ModelSerializer):

    class Meta:

        model = tbl_booking
        fields = ['booking_id', 'booking_type', 'booking_status', 'service_category', 'start_time', 'end_time', 'service_address', 'floor_number', 'zip_code', 'special_instruction', 'daily_rate', 'poster_id', 'createdAt']
        read_only_fields = ['booking_id', 'booking_status', 'poster_id', 'createdAt']

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