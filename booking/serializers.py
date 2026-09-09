from rest_framework import serializers
from .models import tbl_booking, tbl_booking_assignment, tbl_booking_proposal
from django.utils import timezone
from reviews.models import tbl_review
from django.db.models import Avg
import cloudinary.utils


def get_signed_avatar(user):
    if not user:
        return None
    public_id = getattr(user, 'profile_link', None)
    if not public_id:
        return None
    try:
        url, _ = cloudinary.utils.cloudinary_url(
            public_id,
            type="authenticated",
            sign_url=True
        )
        return url
    except Exception:
        return None


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = tbl_booking
        fields = [
            'booking_id',
            'booking_type',
            'booking_status',
            'service_category',
            'start_time',
            'end_time',
            'service_address',
            'floor_number',
            'zip_code',
            'special_instruction',
            'daily_rate',
            'poster_id',
            'createdAt'
        ]
        read_only_fields = ['booking_id', 'booking_status', 'poster_id', 'createdAt']

    def validate(self, data):
        now = timezone.now()
        start_time = data.get('start_time')
        end_time = data.get('end_time')

        if start_time and start_time <= now: 
            raise serializers.ValidationError({"start_time": "Start time must be in the future."})
        
        if end_time and end_time <= now:
            raise serializers.ValidationError({"end_time": "End time must be in the future."})

        if (start_time and end_time) and end_time <= start_time:
            raise serializers.ValidationError({"end_time": "End time must be strictly after the start time."})

        return data


class BookingFeedSerializer(serializers.ModelSerializer):
    profile_link = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    poster_account_type = serializers.SerializerMethodField()

    class Meta:
        model = tbl_booking
        fields = [
            'booking_id',
            'poster_id',
            'poster_account_type',
            'booking_type',
            'booking_status',
            'profile_link',
            'name',
            'service_address',
            'service_category',
            'daily_rate',
            'special_instruction',
            'start_time',
            'end_time',
            'createdAt',
        ]

    def get_poster_account_type(self, obj):
        return getattr(obj.poster_id, 'account_type', 'User')
    
    def get_name(self, obj):
        first_name = obj.poster_id.first_name or ''
        middle_name = obj.poster_id.middle_name or ''
        last_name = obj.poster_id.last_name or ''
        full = f"{first_name} {middle_name} {last_name}".strip()
        return full if full else obj.poster_id.username
    
    def get_profile_link(self, obj):
        return get_signed_avatar(obj.poster_id)


class BookingDetailSerializer(serializers.ModelSerializer):
    poster = serializers.SerializerMethodField()
    assigned_partner = serializers.SerializerMethodField()
    has_reviewed = serializers.SerializerMethodField()
    proposals_count = serializers.SerializerMethodField()

    class Meta:
        model = tbl_booking
        fields = [
            'booking_id',
            'booking_type',
            'booking_status',
            'service_category',
            'start_time',
            'end_time',
            'service_address',
            'floor_number',
            'zip_code',
            'special_instruction',
            'daily_rate',
            'createdAt',
            'poster',
            'assigned_partner',
            'has_reviewed',
            'proposals_count',
        ]

    def get_poster(self, obj):
        user = obj.poster_id
        first = user.first_name or ''
        last = user.last_name or ''
        full_name = f"{first} {last}".strip() or user.username
        
        avg_rating = tbl_review.objects.filter(reviewee_id=user).aggregate(avg=Avg('rating'))['avg']
        rating = round(float(avg_rating), 1) if avg_rating is not None else 5.0

        return {
            'id': str(user.id),
            'name': full_name,
            'account_type': user.account_type,
            'verification_status': user.verification_status,
            'profile_link': get_signed_avatar(user),
            'rating': rating,
            'contact_number': user.contact_number if user.contact_number else None,
        }

    def get_assigned_partner(self, obj):
        assignment = obj.assignments.select_related('accepter_id').first()
        if not assignment or not assignment.accepter_id:
            return None
        user = assignment.accepter_id
        first = user.first_name or ''
        last = user.last_name or ''
        full_name = f"{first} {last}".strip() or user.username
        
        avg_rating = tbl_review.objects.filter(reviewee_id=user).aggregate(avg=Avg('rating'))['avg']
        rating = round(float(avg_rating), 1) if avg_rating is not None else 5.0

        return {
            'id': str(user.id),
            'name': full_name,
            'account_type': user.account_type,
            'verification_status': user.verification_status,
            'profile_link': get_signed_avatar(user),
            'rating': rating,
            'contact_number': user.contact_number if user.contact_number else None,
            'accepted_at': assignment.accepted_at,
        }

    def get_has_reviewed(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        return tbl_review.objects.filter(booking_id=obj, reviewer_id=request.user).exists()

    def get_proposals_count(self, obj):
        return obj.proposals.count()


class BookingProposalSerializer(serializers.ModelSerializer):
    proposer_name = serializers.SerializerMethodField()
    proposer_role = serializers.SerializerMethodField()
    proposer_avatar = serializers.SerializerMethodField()
    proposer_rating = serializers.SerializerMethodField()

    class Meta:
        model = tbl_booking_proposal
        fields = [
            'proposal_id',
            'booking_id',
            'proposer_id',
            'proposer_name',
            'proposer_role',
            'proposer_avatar',
            'proposer_rating',
            'proposed_rate',
            'message',
            'status',
            'createdAt',
        ]
        read_only_fields = ['proposal_id', 'proposer_id', 'status', 'createdAt']

    def get_proposer_name(self, obj):
        first = obj.proposer_id.first_name or ''
        last = obj.proposer_id.last_name or ''
        full_name = f"{first} {last}".strip()
        return full_name if full_name else obj.proposer_id.username

    def get_proposer_role(self, obj):
        return obj.proposer_id.account_type

    def get_proposer_avatar(self, obj):
        return get_signed_avatar(obj.proposer_id)

    def get_proposer_rating(self, obj):
        avg_rating = tbl_review.objects.filter(reviewee_id=obj.proposer_id).aggregate(avg=Avg('rating'))['avg']
        return round(float(avg_rating), 1) if avg_rating is not None else 5.0