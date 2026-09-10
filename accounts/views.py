from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import tbl_user_profile
from .serializers import (
    UserRegistrationSerializer,
    CustomLoginSerializer,
    UserAboutSerializer,
    UserTagsSerializer,
    ContactPrivacySerializer,
    UserSocialLinksSerializer,
    JobStatusSerializer,
    PublicProfileSerializer,
    KasambahayResumeSerializer,
)
from .permissions import IsKasambahay
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.exceptions import Throttled
from django.core.cache import cache
from core.utils import check_valid_uuid
import math
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

class RegistrationThrottle(AnonRateThrottle):
    rate = '5/d'

class UserRegistrationView(APIView):

    throttle_classes = [RegistrationThrottle]

    # This tell Django: "You do not need to logged in to access this windows."
    # (Because if you had to be logged in to register...nobody could ever register!)

    authentication_classes = []
    permission_classes = []

    @extend_schema(
        request=UserRegistrationSerializer,
        parameters=[
            OpenApiParameter(
                name='Idempotency-Key',
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.HEADER,
                description='A unique UUID v4 string to prevent duplicate registrations',
                required=True,
            )
        ]
    )

    def post(self, request):

        # Look for the special header send by the frontend (or Postman)
        idempotency_key = request.headers.get('Idempotency-Key')

        # If they sent a key, check if we already saved an answer for it
        if not idempotency_key or not check_valid_uuid(idempotency_key):

            return Response({"details": "The Idempotency-Key header is required and must be a valid UUID v4."}, 
                status=status.HTTP_400_BAD_REQUEST)
        
        cached_response = cache.get(idempotency_key)

        if cached_response:
            # They Double Clicked! Give them the cached answer
            return Response(cached_response['data'], status=cached_response['status'])


        # 1. Give the incoming JSON data to our bouncer (the Serializer)
        
        serializer = UserRegistrationSerializer(data=request.data)

        # 2. The bouncer checks if the data matches the blueprint perfeclty

        if serializer.is_valid():

            # 3. If valid, encrpyt the password and save to the database

            user = serializer.save()

            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = CustomLoginSerializer.get_token(user)

            response_data = {
                "message": "Account created successfully",
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            }
            response_status = status.HTTP_201_CREATED
            
            # Trap the double-click: Save the answer in the cache for 24 hours
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
            
        # If invalid (e.g., missing an email), send the exact error back

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def throttled(self, request, wait):        
        # 3600 seconds = 1 hour
        if wait > 3600: 
            time_left = math.ceil(wait / 3600)
            custom_message = f"Too many attempts. Please try again in {time_left} hours."

        else:
            custom_message = f"Too many attempts. Please try again in {math.ceil(wait/60)} minutes."

        raise Throttled(detail=custom_message)


class LoginThrottle(AnonRateThrottle):
    """
    Implements a Sliding Window rate limit for login attempts.
    This throttle prevents brute-force attacks by limiting the number of 
    failed login attempts an anonymous user can make. It uses a sliding 
    window algorithm rather than a fixed clock, meaning the restriction 
    only lifts when the oldest failed attempt falls out of the time window.
    Attributes:
        rate (str): Set to 'custom' to bypass DRF's default s/m/h/d parser.
    """
    
    rate = 'custom'
    
    def parse_rate(self, rate):
        """
        Overrides the default string parser to enforce exact math.
        
        Returns:
            tuple: (number_of_attempts, cooldown_in_seconds)
                   Currently set to 5 attempts per 300 seconds (5 minutes).
        """
        return (5, 300)

class CustomLoginView(TokenObtainPairView):
    """
    Secure login endpoint utilizing JWT authentication and brute-force protection.
    Inherits from SimpleJWT's TokenObtainPairView to generate Access and 
    Refresh tokens. It applies a custom serializer to format error messages 
    and a rate throttle to lock out abusive traffic.
    Attributes:
        serializer_class (Serializer): Custom serializer for user-friendly 401 errors.
        throttle_classes (list): Applies the LoginThrottle sliding window limit.
    """
    serializer_class = CustomLoginSerializer
    throttle_classes = [LoginThrottle]
    def throttled(self, request, wait):
        """
        Intercepts the default throttle exception to provide a custom UI message.
        Args:
            request (Request): The incoming HTTP request.
            wait (int): The number of seconds remaining before the throttle lifts.
        Raises:
            Throttled: Returns a 429 Too Many Requests with a user-friendly 
                       wait time rounded up to the nearest minute.
        """
        custom_message = f"Too many attempts. Please try again in {math.ceil(wait/60)} minutes."
        raise Throttled(detail=custom_message)

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import ProfileImageUploadSerializer


class AdminUserListView(generics.ListAPIView):
    """
    Returns registered users formatted for the Admin User Directory dashboard.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        role_param = request.query_params.get('role')
        barangay_param = request.query_params.get('barangay')
        users_qs = tbl_user_profile.objects.filter(account_type__in=['Homeowner', 'Kasambahay']).order_by('-date_joined')

        if role_param and role_param.upper() != 'ALL':
            users_qs = users_qs.filter(account_type__iexact=role_param)

        if barangay_param and barangay_param.upper() not in ['ALL', 'ALL BARANGAYS']:
            from django.db.models import Q
            users_qs = users_qs.filter(
                Q(city__icontains=barangay_param) |
                Q(street__icontains=barangay_param)
            )

        data = []
        for u in users_qs:
            full_name = f"{u.first_name} {u.last_name}".strip() or u.username
            role_norm = u.account_type.upper() if u.account_type else 'HOMEOWNER'
            if role_norm not in ['HOMEOWNER', 'KASAMBAHAY']:
                role_norm = 'HOMEOWNER'

            avatar = u.profile_link or f"https://ui-avatars.com/api/?name={u.first_name}+{u.last_name}&background=F5A623&color=fff"
            if u.profile_link and not (u.profile_link.startswith('http://') or u.profile_link.startswith('https://')):
                try:
                    import cloudinary.utils
                    temp_url, _ = cloudinary.utils.cloudinary_url(
                        u.profile_link,
                        type="authenticated",
                        sign_url=True,
                    )
                    avatar = temp_url
                except Exception:
                    pass
            is_verified = u.verification_status == 'Verified'

            brgy = 'Pagatpat'
            street_lower = (u.street or '').lower()
            city_lower = (u.city or '').lower()
            for b in ['Pagatpat', 'Canitoan']:
                if b.lower() in street_lower or b.lower() in city_lower:
                    brgy = b
                    break

            user_item = {
                "id": str(u.id),
                "name": full_name,
                "role": role_norm,
                "avatar": avatar,
                "email": u.email,
                "contactNumber": u.contact_number or "+639123456789",
                "address": f"{u.street or ''}, {u.city or 'Cagayan de Oro City'}".strip(', '),
                "barangay": brgy,
                "city": u.city or "Cagayan de Oro City",
                "verified": is_verified,
                "status": "ACTIVE" if u.is_active else "SUSPENDED",
                "joinedDate": u.date_joined.strftime('%b %d, %Y') if u.date_joined else "Recent",
                "completedJobs": 0,
                "sentimentScore": {
                    "positive": 95,
                    "neutral": 5,
                    "negative": 0
                },
                "ra10361Compliant": True,
            }
            data.append(user_item)

        return Response(data, status=status.HTTP_200_OK)


class AdminDashboardStatsView(APIView):
    """
    Provides real-time aggregated metrics directly from the database for the SerbiSure Admin dashboard.
    Supports citywide view (Superadmin) and barangay-scoped view (Local LGU).
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        barangay_param = request.query_params.get('barangay')
        
        workers_qs = tbl_user_profile.objects.filter(account_type='Kasambahay')
        homeowners_qs = tbl_user_profile.objects.filter(account_type='Homeowner')
        
        if barangay_param and barangay_param.upper() not in ['ALL', 'ALL BARANGAYS']:
            from django.db.models import Q
            workers_qs = workers_qs.filter(
                Q(city__icontains=barangay_param) | Q(street__icontains=barangay_param)
            )
            homeowners_qs = homeowners_qs.filter(
                Q(city__icontains=barangay_param) | Q(street__icontains=barangay_param)
            )

        total_workers = workers_qs.count()
        total_homeowners = homeowners_qs.count()
        
        # Calculate employed workers from active booking assignments OR self-marked is_on_job
        from booking.models import tbl_booking_assignment, tbl_booking
        active_booking_ids = tbl_booking.objects.filter(
            booking_status__in=['Accepted', 'InProgress']
        ).values_list('booking_id', flat=True)
        
        assigned_worker_ids = tbl_booking_assignment.objects.filter(
            booking_id__in=active_booking_ids
        ).values_list('accepter_id', flat=True).distinct()
        
        from django.db.models import Q
        employed = workers_qs.filter(
            Q(is_on_job=True) | Q(id__in=assigned_worker_ids)
        ).distinct().count()
        available = max(0, total_workers - employed)
        employment_ratio = round((employed / total_workers * 100)) if total_workers > 0 else 0

        # Dynamic Barangay Breakdowns
        barangay_breakdown = []
        for b_name in ['Pagatpat', 'Canitoan']:
            b_workers = tbl_user_profile.objects.filter(
                account_type='Kasambahay'
            ).filter(
                Q(city__icontains=b_name) | Q(street__icontains=b_name)
            )
            b_total = b_workers.count()
            b_employed = b_workers.filter(
                Q(is_on_job=True) | Q(id__in=assigned_worker_ids)
            ).distinct().count()
            b_avail = max(0, b_total - b_employed)
            b_ratio = round((b_employed / b_total * 100)) if b_total > 0 else 0
            barangay_breakdown.append({
                "name": b_name,
                "totalWorkers": b_total,
                "employed": b_employed,
                "available": b_avail,
                "employmentRatio": b_ratio,
                "status": "ACTIVE"
            })

        # Pending verification queue count
        from verifications.models import tbl_documents
        pending_verifications = tbl_documents.objects.filter(
            verification_status='Pending'
        ).count()

        return Response({
            "metrics": {
                "totalWorkers": total_workers,
                "totalEmployed": employed,
                "totalAvailable": available,
                "employmentRatio": employment_ratio,
                "totalHomeowners": total_homeowners,
                "pendingVerifications": pending_verifications,
            },
            "barangays": barangay_breakdown,
        }, status=status.HTTP_200_OK)


class ProfileImageUploadThrottle(UserRateThrottle):
    scope = 'profile_image_upload'
    rate = '2/h'

class ProfileImageUploadView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)
    serializer_class = ProfileImageUploadSerializer
    throttle_classes = [ProfileImageUploadThrottle]

    def get_object(self):
        # We automatically return the logged-in user!
        return self.request.user

    def throttled(self, request, wait):        
    # 3600 seconds = 1 hour
        if wait > 3600: 
            time_left = math.ceil(wait / 3600)
            custom_message = f"Too many attempts. Please try again in {time_left} hours."

        else:
            custom_message = f"Too many attempts. Please try again in {math.ceil(wait/60)} minutes."

        raise Throttled(detail=custom_message)


class UserAboutThrottle(UserRateThrottle):
    scope = 'user_about'
    rate = '3/h'

class UserAboutView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserAboutSerializer

    def get_throttles(self):
        if self.request.method in ['PATCH', 'PUT']:
            return [UserAboutThrottle()]
        return []

    def get_object(self):
        return self.request.user

    def throttled(self, request, wait):        
        # 3600 seconds = 1 hour
        if wait > 3600: 
            time_left = math.ceil(wait / 3600)
            custom_message = f"Too many attempts. Please try again in {time_left} hours."

        else:
            custom_message = f"Too many attempts. Please try again in {math.ceil(wait/60)} minutes."

        raise Throttled(detail=custom_message)

class UserTagsThrottle(UserRateThrottle):
    scope = 'user_tags'
    rate = '60/h'

class UserTagsView(generics.RetrieveUpdateAPIView):

    permission_classes = [IsAuthenticated]
    serializer_class = UserTagsSerializer
    throttle_classes = [UserTagsThrottle]

    def get_object(self):
        return self.request.user
    
    def throttled(self, request, wait):        
        # 3600 seconds = 1 hour
        if wait > 3600: 
            time_left = math.ceil(wait / 3600)
            custom_message = f"Too many attempts. Please try again in {time_left} hours."

        else:
            custom_message = f"Too many attempts. Please try again in {math.ceil(wait/60)} minutes."

        raise Throttled(detail=custom_message)


class ContactPrivacyView(generics.RetrieveUpdateAPIView):
    """
    Get or update contact number visibility for the authenticated user.
    GET/PATCH /api/v1/accounts/contact-privacy/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ContactPrivacySerializer

    def get_object(self):
        return self.request.user


class UserSocialLinksThrottle(UserRateThrottle):
    scope = 'user_social_links'
    rate = '30/h'


class UserSocialLinksView(generics.RetrieveUpdateAPIView):
    """
    Get (GET) or update (PATCH, PUT) social accounts and contact links for the authenticated user.
    GET/PATCH /api/v1/accounts/social-links/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSocialLinksSerializer
    throttle_classes = [UserSocialLinksThrottle]

    def get_object(self):
        return self.request.user

    def throttled(self, request, wait):
        if wait > 3600:
            time_left = math.ceil(wait / 3600)
            custom_message = f"Too many attempts. Please try again in {time_left} hours."
        else:
            custom_message = f"Too many attempts. Please try again in {math.ceil(wait / 60)} minutes."
        raise Throttled(detail=custom_message)


class JobStatusView(generics.RetrieveUpdateAPIView):
    """
    Get or update Kasambahay availability / job status.
    GET/PATCH /api/v1/accounts/job-status/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = JobStatusSerializer

    def get_object(self):
        return self.request.user

class PublicProfileView(generics.RetrieveAPIView):
    """
    Read-only public profile for any user by UUID.
    Only accessible by authenticated users.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PublicProfileSerializer
    lookup_field = 'id'
    queryset = tbl_user_profile.objects.filter(is_active=True)


class ResumeUploadThrottle(UserRateThrottle):
    scope = 'resume_upload'
    rate = '5/d'


class KasambahayResumeView(generics.RetrieveUpdateAPIView):
    """
    Endpoint for Kasambahay users to retrieve (GET) and upload/update (PATCH, POST) their PDF resume.
    - Only Kasambahay accounts are authorized (403 for others).
    - Rate-limited to 5 uploads per day on write operations (GET is unthrottled).
    - Supports Idempotency-Key header on write operations.
    """
    permission_classes = [IsAuthenticated, IsKasambahay]
    parser_classes = (MultiPartParser, FormParser)
    serializer_class = KasambahayResumeSerializer

    def get_throttles(self):
        if self.request.method in ['PATCH', 'PUT', 'POST']:
            return [ResumeUploadThrottle()]
        return []

    def get_object(self):
        return self.request.user

    def post(self, request, *args, **kwargs):
        return self.patch(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        idempotency_key = request.headers.get('Idempotency-Key')
        cache_key = None
        if idempotency_key:
            if not check_valid_uuid(idempotency_key):
                return Response(
                    {"details": "The Idempotency-Key header must be a valid UUID v4."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            cache_key = f"resume_idemp_{request.user.id}_{idempotency_key}"
            cached = cache.get(cache_key)
            if cached:
                return Response(cached['data'], status=cached['status'])

        response = super().patch(request, *args, **kwargs)

        if cache_key and response.status_code == status.HTTP_200_OK:
            cache.set(
                cache_key,
                {'data': response.data, 'status': response.status_code},
                timeout=86400
            )

        return response

    def throttled(self, request, wait):        
        # 3600 seconds = 1 hour
        if wait > 3600: 
            time_left = math.ceil(wait / 3600)
            custom_message = f"Too many attempts. Please try again in {time_left} hours."
        else:
            custom_message = f"Too many attempts. Please try again in {math.ceil(wait/60)} minutes."

        raise Throttled(detail=custom_message)


class ChangePasswordView(APIView):
    """
    Endpoint allowing authenticated users to change their password.
    Requires current_password, new_password, and confirm_password.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        if not current_password or not new_password or not confirm_password:
            return Response(
                {'error': 'Current password, new password, and confirmation are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_password != confirm_password:
            return Response({'error': 'New passwords do not match.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({'error': 'Password must be at least 8 characters long.'}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.check_password(current_password):
            return Response({'error': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

        if current_password == new_password:
            return Response({'error': 'New password must be different from current password.'}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save()
        return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)


class UserSearchView(APIView):
    """
    Search active users by query keyword, account type (Kasambahay / Homeowner),
    city, province, or tags (Tier 2-2).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        role = request.query_params.get('role', '').strip()
        location = request.query_params.get('location', '').strip()
        tag = request.query_params.get('tag', '').strip()

        qs = tbl_user_profile.objects.filter(is_active=True).exclude(id=request.user.id)

        if role:
            qs = qs.filter(account_type__iexact=role)
        
        if location:
            qs = qs.filter(Q(city__icontains=location) | Q(province__icontains=location) | Q(street__icontains=location))

        if tag:
            qs = qs.filter(user_tags__icontains=tag)

        if query:
            qs = qs.filter(
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(user_about__icontains=query) |
                Q(city__icontains=query) |
                Q(user_tags__icontains=query)
            )

        serializer = PublicProfileSerializer(qs[:30], many=True)
        return Response({'users': serializer.data, 'count': qs.count()}, status=status.HTTP_200_OK)


class DeleteAccountView(APIView):
    """
    Soft-deletes and deactivates the authenticated user's account (Tier 3-5).
    Requires the current password to confirm the critical operation.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        password = request.data.get('password')
        if not password:
            return Response({'error': 'Password is required to confirm account deletion.'}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.check_password(password):
            return Response({'error': 'Incorrect password.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        user.is_active = False
        user.user_about = '[Account Deactivated]'
        user.contact_number = '+639000000000'
        user.user_tags = []
        user.save()

        return Response({'message': 'Your account has been deactivated successfully.'}, status=status.HTTP_200_OK)


class ExportUserDataView(APIView):
    """
    Exports a GDPR-style archive of the user's personal data (Tier 3-5).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        from booking.models import tbl_booking, tbl_booking_assignment
        from reviews.models import tbl_review

        posted_bookings = list(tbl_booking.objects.filter(poster_id=user).values(
            'booking_id', 'booking_type', 'booking_status', 'service_category', 'daily_rate', 'service_address', 'createdAt'
        ))
        for b in posted_bookings:
            b['booking_id'] = str(b['booking_id'])
            b['createdAt'] = str(b['createdAt'])
            b['daily_rate'] = str(b['daily_rate'])

        assigned_bookings = list(tbl_booking_assignment.objects.filter(accepter_id=user).values(
            'booking_assignment_id', 'booking_id', 'accepted_at'
        ))
        for a in assigned_bookings:
            a['booking_assignment_id'] = str(a['booking_assignment_id'])
            a['booking_id'] = str(a['booking_id'])
            a['accepted_at'] = str(a['accepted_at'])

        reviews_given = list(tbl_review.objects.filter(reviewer_id=user).values(
            'review_id', 'rating', 'unstructured_feedback', 'nlp_sentiment', 'createdAt'
        ))
        for r in reviews_given:
            r['review_id'] = str(r['review_id'])
            r['createdAt'] = str(r['createdAt'])

        reviews_received = list(tbl_review.objects.filter(reviewee_id=user).values(
            'review_id', 'rating', 'unstructured_feedback', 'nlp_sentiment', 'createdAt'
        ))
        for r in reviews_received:
            r['review_id'] = str(r['review_id'])
            r['createdAt'] = str(r['createdAt'])

        data = {
            'profile': {
                'id': str(user.id),
                'email': user.email,
                'first_name': user.first_name,
                'middle_name': user.middle_name,
                'last_name': user.last_name,
                'account_type': user.account_type,
                'verification_status': user.verification_status,
                'contact_number': user.contact_number,
                'user_about': user.user_about,
                'user_tags': user.user_tags,
                'city': user.city,
                'province': user.province,
                'date_joined': str(user.date_joined),
            },
            'posted_bookings': posted_bookings,
            'assigned_bookings': assigned_bookings,
            'reviews_given': reviews_given,
            'reviews_received': reviews_received,
        }

        return Response({'user_data': data}, status=status.HTTP_200_OK)
